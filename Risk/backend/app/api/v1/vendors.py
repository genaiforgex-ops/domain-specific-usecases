import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.models.vendor import DDReport, DDFinding, Vendor
from app.schemas.vendor import (
    DDFindingResponse,
    DDFindingUpdate,
    DDReportResponse,
    VendorCreate,
    VendorResponse,
)
from app.services.reporting_service import ReportingService
from app.services.vendor_service import VendorService
from app.workers.tasks import run_vendor_dd_bg

router = APIRouter(tags=["vendors"])


@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:read")),
):
    svc = VendorService(db)
    return await svc.list_vendors(q)


@router.post("/vendors", response_model=VendorResponse)
async def create_vendor(
    body: VendorCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:create")),
):
    svc = VendorService(db)
    try:
        return await svc.create_vendor(body.model_dump(), user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:read")),
):
    result = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    return vendor


@router.get("/vendors/{vendor_id}/dd-reports/latest", response_model=DDReportResponse)
async def latest_dd_report(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:read")),
):
    """Most recent report for a vendor, so the UI can show the saved
    snapshot instead of re-screening (which would give slightly different
    live-search results each time)."""
    result = await db.execute(
        select(DDReport)
        .options(selectinload(DDReport.findings))
        .where(DDReport.vendor_id == vendor_id)
        .order_by(DDReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "No report for this vendor yet")
    return report


@router.post("/vendors/{vendor_id}/dd-runs", response_model=DDReportResponse)
async def start_dd_run(
    vendor_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:create")),
):
    svc = VendorService(db)

    # A screening already in flight is returned as-is rather than duplicated.
    # This is the durable guard: the UI can double-click, be open in two tabs,
    # or reload mid-run, and any of those used to queue another full Gemini
    # screening for the same vendor.
    active = await svc.find_active_run(vendor_id)
    if active:
        await db.commit()
        result = await db.execute(
            select(DDReport).options(selectinload(DDReport.findings)).where(DDReport.id == active.id)
        )
        return result.scalar_one()

    try:
        report = await svc.create_dd_report(vendor_id, user.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e

    # Scrape + Gemini can take 30-60s, so run the DD off the request path via a
    # background task (same in every environment) rather than blocking the response
    # and risking a proxy 504. Commit first so the task's own DB session sees the
    # report row; the frontend polls the report for results.
    await db.commit()
    background_tasks.add_task(run_vendor_dd_bg, str(report.id))

    result = await db.execute(
        select(DDReport).options(selectinload(DDReport.findings)).where(DDReport.id == report.id)
    )
    return result.scalar_one()


@router.get("/dd-reports/{report_id}", response_model=DDReportResponse)
async def get_dd_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:read")),
):
    result = await db.execute(
        select(DDReport)
        .options(selectinload(DDReport.findings))
        .where(DDReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.patch("/findings/{finding_id}", response_model=DDFindingResponse)
async def update_finding(
    finding_id: uuid.UUID,
    body: DDFindingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:review")),
):
    result = await db.execute(select(DDFinding).where(DDFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(404, "Finding not found")
    finding.disposition = body.disposition
    await db.flush()
    return finding


@router.post("/dd-reports/{report_id}/sign-off", response_model=DDReportResponse)
async def sign_off_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:approve")),
):
    svc = VendorService(db)
    report = await svc.sign_off_report(report_id, user.id)
    result = await db.execute(
        select(DDReport).options(selectinload(DDReport.findings)).where(DDReport.id == report.id)
    )
    return result.scalar_one()


@router.get("/dd-reports/{report_id}/export.pdf")
async def export_dd_pdf(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m2:read")),
):
    svc = ReportingService(db)
    pdf = await svc.generate_dd_pdf(report_id)
    return Response(content=pdf, media_type="application/pdf")
