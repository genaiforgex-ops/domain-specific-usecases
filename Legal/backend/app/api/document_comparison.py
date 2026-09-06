"""UC-02 Document Comparison — compare any two uploaded documents (not MSA versions)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.comparison import DocumentComparison
from app.models.user import User
from app.schemas.comparison import ComparisonCreate, ComparisonOut, ComparisonSummary
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.document_parser import DocumentParseError, parse_document


router = APIRouter(prefix="/api/document-comparison", tags=["document-comparison"])

_ALLOWED_EXT = {".pdf", ".docx", ".doc", ".txt", ".md"}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _ext_ok(filename: str) -> bool:
    name = (filename or "").lower()
    return any(name.endswith(ext) for ext in _ALLOWED_EXT)


async def _extract_upload(upload: UploadFile, *, side: str) -> tuple[str, str]:
    """Return (filename, extracted_text) or raise HTTPException."""
    filename = (upload.filename or f"{side}.txt").strip() or f"{side}.txt"
    if not _ext_ok(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{side}: unsupported file type. Use PDF, DOCX, or TXT.",
        )
    data = await upload.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{side}: file is empty.",
        )
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{side}: file exceeds 50 MB limit.",
        )
    try:
        text = parse_document(data, filename, upload.content_type)
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{side}: could not read file — {exc}",
        ) from exc
    if not (text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{side}: no extractable text found in the file.",
        )
    return filename, text.strip()


def _persist_comparison(
    *,
    db: Session,
    user: User,
    request: Request,
    label: str,
    v1_filename: str,
    v2_filename: str,
    v1_text: str,
    v2_text: str,
) -> DocumentComparison:
    result = orch_tasks.compare_documents(v1_text, v2_text)
    comparison = DocumentComparison(
        label=label,
        v1_filename=v1_filename,
        v2_filename=v2_filename,
        v1_text=v1_text,
        v2_text=v2_text,
        diff_blocks=[asdict(b) for b in result.diff_blocks],
        risk_commentary=[asdict(f) for f in result.risk_commentary],
        summary_report=result.summary_report,
        model_version=result.model_version,
        created_by_id=user.id,
    )
    db.add(comparison)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="documents_compared",
        module="document_comparison",
        input_summary=f"doc_a={v1_filename} doc_b={v2_filename}",
        ai_output_summary=result.summary_report,
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=comparison.id,
    )
    db.commit()
    db.refresh(comparison)
    return comparison


@router.get("", response_model=list[ComparisonSummary])
def list_comparisons(
    _: User = Depends(require_permission(Permission.DOCUMENT_COMPARISON)),
    db: Session = Depends(get_db),
) -> list[ComparisonSummary]:
    # Standalone Doc Comparison only — MSA negotiation diffs stay in MSA Automation.
    rows = (
        db.execute(
            select(DocumentComparison)
            .where(DocumentComparison.tracker_id.is_(None))
            .order_by(DocumentComparison.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ComparisonSummary.model_validate(c) for c in rows]


@router.post("", response_model=ComparisonOut, status_code=status.HTTP_201_CREATED)
def create_comparison(
    payload: ComparisonCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.DOCUMENT_COMPARISON)),
    db: Session = Depends(get_db),
) -> ComparisonOut:
    if not payload.v1_text.strip() or not payload.v2_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both documents must contain text",
        )
    comparison = _persist_comparison(
        db=db,
        user=user,
        request=request,
        label=payload.label,
        v1_filename=payload.v1_filename,
        v2_filename=payload.v2_filename,
        v1_text=payload.v1_text,
        v2_text=payload.v2_text,
    )
    return ComparisonOut.model_validate(comparison)


@router.post("/upload", response_model=ComparisonOut, status_code=status.HTTP_201_CREATED)
async def create_comparison_from_uploads(
    request: Request,
    label: str = Form(...),
    file_a: UploadFile = File(..., description="First document (PDF, DOCX, or TXT)"),
    file_b: UploadFile = File(..., description="Second document (PDF, DOCX, or TXT)"),
    user: User = Depends(require_permission(Permission.DOCUMENT_COMPARISON)),
    db: Session = Depends(get_db),
) -> ComparisonOut:
    """Compare two uploaded files. Prefer this over pasting text.

    Not for MSA negotiation versions — use MSA Automation for vendor redlines.
    """
    clean_label = (label or "").strip()
    if not clean_label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label is required")

    v1_filename, v1_text = await _extract_upload(file_a, side="Document A")
    v2_filename, v2_text = await _extract_upload(file_b, side="Document B")

    comparison = _persist_comparison(
        db=db,
        user=user,
        request=request,
        label=clean_label,
        v1_filename=v1_filename,
        v2_filename=v2_filename,
        v1_text=v1_text,
        v2_text=v2_text,
    )
    return ComparisonOut.model_validate(comparison)


@router.get("/{comparison_id}", response_model=ComparisonOut)
def get_comparison(
    comparison_id: int,
    _: User = Depends(require_permission(Permission.DOCUMENT_COMPARISON)),
    db: Session = Depends(get_db),
) -> ComparisonOut:
    comparison = db.get(DocumentComparison, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")
    return ComparisonOut.model_validate(comparison)
