import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.factory import get_osint_adapter
from app.adapters.protocols import OSINTFinding
from app.audit.service import AuditService
from app.models.vendor import DDReport, DDFinding, DDWeightConfig, Vendor
from app.services.classification_service import ClassificationService
from app.services.usage_service import record_llm_usage

# Numeric severity per model-reported severity string.
_SEVERITY_WEIGHT = {"critical": 10.0, "high": 8.0, "medium": 5.0, "low": 2.0}
_PASS_STATUSES = {"pass", "low", "not run", "clean", "ok", "verified", ""}

# A screening older than this cannot still be running: the Gemini call is
# capped at 120s and the scrape adds only seconds on top.
STALE_RUN_AFTER = timedelta(minutes=10)


def _sev(value: str, default: float = 5.0) -> float:
    return _SEVERITY_WEIGHT.get((value or "").strip().lower(), default)


def derive_findings_from_audit(audit: dict) -> list[OSINTFinding]:
    """Flatten the rich audit into discrete DD findings (the evidence list).

    Categories match the frontend labels: sanctions, regulatory_action,
    litigation, adverse_media, financial_distress, ownership, security,
    web_presence.
    """
    findings: list[OSINTFinding] = []
    legal = audit.get("legal") or {}

    for lit in legal.get("litigations") or []:
        if not isinstance(lit, dict):
            continue
        lit_type = (lit.get("type") or "").lower()
        court = (lit.get("court") or "").lower()
        is_sanction = "sanction" in lit_type or "watchlist" in lit_type or "sdn" in court
        findings.append(OSINTFinding(
            category="sanctions" if is_sanction else "litigation",
            title=lit.get("type") or ("Sanctions match" if is_sanction else "Litigation"),
            summary=" · ".join(x for x in [
                lit.get("summary"),
                f"Parties: {lit.get('parties')}" if lit.get("parties") else None,
                f"Case: {lit.get('case_number')}" if lit.get("case_number") else None,
                f"Status: {lit.get('status')}" if lit.get("status") else None,
            ] if x),
            source_tier="primary",
            source_url=lit.get("url") or "",
            severity_weight=10.0 if is_sanction else 6.0,
        ))

    for news in legal.get("news") or []:
        if not isinstance(news, dict):
            continue
        findings.append(OSINTFinding(
            category="adverse_media",
            title=news.get("headline") or "Adverse media",
            summary=" · ".join(x for x in [
                news.get("summary"),
                f"{news.get('source')} ({news.get('date')})" if news.get("source") else None,
            ] if x),
            source_tier="secondary",
            source_url=news.get("url") or "",
            severity_weight=3.0,
        ))

    security = audit.get("security") or {}
    for inc in security.get("incident_history") or []:
        if not isinstance(inc, dict):
            continue
        findings.append(OSINTFinding(
            category="regulatory_action",
            title=inc.get("event") or "Security / regulatory incident",
            summary=" · ".join(x for x in [inc.get("summary"), inc.get("status"), inc.get("date")] if x),
            source_tier="primary",
            source_url="",
            severity_weight=6.0,
        ))

    for vapt in security.get("vapt_findings") or []:
        if not isinstance(vapt, dict):
            continue
        sev = (vapt.get("severity") or "").lower()
        if sev in ("high", "critical"):
            findings.append(OSINTFinding(
                category="security",
                title=vapt.get("category") or "Security vulnerability",
                summary=vapt.get("description") or "",
                source_tier="secondary",
                source_url="",
                severity_weight=_sev(sev),
            ))

    for source_name, data in (security.get("reputation_sources") or {}).items():
        if isinstance(data, dict) and (data.get("detections") or 0) > 0:
            findings.append(OSINTFinding(
                category="security",
                title=f"Threat-intel hit: {source_name}",
                summary=f"{data.get('detections')} detection(s) — status {data.get('status')}",
                source_tier="secondary",
                source_url="",
                severity_weight=5.0,
            ))

    for check_name, check in (audit.get("compliance_checks") or {}).items():
        if not isinstance(check, dict):
            continue
        status = (check.get("status") or "").strip().lower()
        if status and status not in _PASS_STATUSES:
            findings.append(OSINTFinding(
                category="web_presence",
                title=f"Compliance issue: {check_name.replace('_', ' ')}",
                summary=f"{check.get('status')} — {check.get('details') or ''}".strip(" —"),
                source_tier="secondary",
                source_url="",
                severity_weight=2.0,
            ))

    footprint = audit.get("footprint") or {}
    for rel in footprint.get("discovered_relations") or []:
        if not isinstance(rel, dict):
            continue
        risk = (rel.get("risk_rating") or "").lower()
        if risk in ("high", "critical", "medium"):
            findings.append(OSINTFinding(
                category="ownership",
                title=f"Linked entity: {rel.get('entity_name') or 'unknown'}",
                summary=" · ".join(x for x in [
                    rel.get("relationship_type"),
                    f"Shared: {rel.get('shared_asset')}" if rel.get("shared_asset") else None,
                ] if x),
                source_tier="secondary",
                source_url=rel.get("url") or "",
                severity_weight=_sev(risk, 4.0),
            ))

    return findings


class VendorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_log = AuditService(db)
        self.osint = get_osint_adapter()

    async def create_vendor(self, data: dict, created_by: uuid.UUID) -> Vendor:
        if data.get("cin"):
            existing = await self.db.execute(
                select(Vendor).where(Vendor.cin == data["cin"])
            )
            if existing.scalar_one_or_none():
                raise ValueError("Vendor with this CIN already exists")
        if data.get("pan"):
            existing = await self.db.execute(
                select(Vendor).where(Vendor.pan == data["pan"])
            )
            if existing.scalar_one_or_none():
                raise ValueError("Vendor with this PAN already exists")

        vendor = Vendor(
            legal_name=data["legal_name"],
            country=data.get("country", "IN"),
            cin=data.get("cin"),
            pan=data.get("pan"),
            gstin=data.get("gstin"),
            website=data.get("website"),
            registered_address=data.get("registered_address"),
            search_vector=f"{data['legal_name']} {data.get('cin', '')} {data.get('pan', '')}",
        )
        self.db.add(vendor)
        await self.db.flush()
        await self.audit_log.log("vendor.created", "vendor", str(vendor.id), actor_id=created_by)
        return vendor

    async def list_vendors(self, q: str | None = None) -> list[Vendor]:
        stmt = select(Vendor).order_by(Vendor.created_at.desc())
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Vendor.legal_name.ilike(pattern),
                    Vendor.cin.ilike(pattern),
                    Vendor.pan.ilike(pattern),
                )
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_weights(self) -> DDWeightConfig:
        result = await self.db.execute(
            select(DDWeightConfig).where(DDWeightConfig.is_active.is_(True)).limit(1)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise ValueError("No active DD weight config")
        return config

    def _dedupe_hash(self, title: str, source_url: str) -> str:
        normalized = f"{title.lower().strip()}|{(source_url or '').lower()}"
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def find_active_run(self, vendor_id: uuid.UUID) -> DDReport | None:
        """The screening already in flight for this vendor, if any.

        Callers reuse it instead of starting a second one. Without this, opening
        a vendor whose run had not finished queued another full screening — the
        history shows one vendor accumulating four runs in nineteen seconds.

        A run older than the cutoff cannot still be alive (the Gemini call itself
        is capped at two minutes), so it is reaped as failed rather than left to
        block this vendor from ever being screened again.
        """
        result = await self.db.execute(
            select(DDReport)
            .where(DDReport.vendor_id == vendor_id, DDReport.status == "processing")
            .order_by(DDReport.created_at.desc())
        )
        cutoff = datetime.now(timezone.utc) - STALE_RUN_AFTER
        active = None
        for report in result.scalars().all():
            created = report.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created is not None and created > cutoff and active is None:
                active = report
            elif created is None or created <= cutoff:
                report.status = "failed"
                report.error = "Screening did not complete — the run was interrupted."
        await self.db.flush()
        return active

    async def create_dd_report(self, vendor_id: uuid.UUID, created_by: uuid.UUID) -> DDReport:
        """Create the report row in 'processing' state. Instant — the heavy
        scrape + Gemini work happens in run_dd (scheduled as a background task)."""
        result = await self.db.execute(select(Vendor).where(Vendor.id == vendor_id))
        vendor = result.scalar_one_or_none()
        if not vendor:
            raise ValueError("Vendor not found")

        weight_config = await self.get_active_weights()
        report = DDReport(
            vendor_id=vendor_id,
            status="processing",
            weights_version=weight_config.version,
            created_by=created_by,
        )
        self.db.add(report)
        await self.db.flush()
        await self.audit_log.log("dd.started", "dd_report", str(report.id), actor_id=created_by)
        return report

    async def run_dd(self, report_id: uuid.UUID) -> DDReport:
        """Run the actual due-diligence audit for an already-created report."""
        result = await self.db.execute(select(DDReport).where(DDReport.id == report_id))
        report = result.scalar_one()
        vendor_result = await self.db.execute(select(Vendor).where(Vendor.id == report.vendor_id))
        vendor = vendor_result.scalar_one()

        try:
            audit = await self.osint.audit({
                "legal_name": vendor.legal_name,
                "website": vendor.website,
                "cin": vendor.cin,
                "pan": vendor.pan,
                "country": vendor.country,
            })
        except Exception as exc:  # keep the report row, surface the failure
            report.status = "failed"
            report.error = str(exc)
            await self.db.flush()
            return report

        report.audit_data = audit

        # An audit that came back with _error carries no real findings and a
        # zero score. Storing that as "ready" presented a blank report as a
        # completed screening — indistinguishable from a genuine all-clear.
        # Record the usage first, since the failed call still cost tokens.
        audit_error = audit.get("_error")

        usage = audit.get("_usage") or {}
        await record_llm_usage(
            self.db,
            actor_id=report.created_by,
            module="M2",
            operation="audit",
            vendor_id=report.vendor_id,
            model_version=audit.get("_model_version") or "unknown",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

        if audit_error:
            report.status = "failed"
            report.error = (audit.get("risk") or {}).get("summary") or audit_error
            await self.db.flush()
            return report

        osint_findings = derive_findings_from_audit(audit)
        seen_hashes: set[str] = set()
        findings: list[DDFinding] = []
        for item in osint_findings:
            dh = self._dedupe_hash(item.title, item.source_url)
            if dh in seen_hashes:
                continue
            seen_hashes.add(dh)
            finding = DDFinding(
                report_id=report.id,
                category=item.category,
                title=item.title,
                summary=item.summary,
                source_tier=item.source_tier,
                source_url=item.source_url,
                dedupe_hash=dh,
                severity_weight=item.severity_weight,
            )
            self.db.add(finding)
            findings.append(finding)

        # Score is the screening agent's synthesised 0-100 risk judgement.
        model_score = (audit.get("risk") or {}).get("score")
        report.red_flag_score = (
            min(100.0, round(float(model_score), 2))
            if isinstance(model_score, (int, float)) else 0.0
        )

        # Optional M1 link: if the vendor was already classified as an
        # outsourcing arrangement, append the extra checklist. This is a
        # nice-to-have — never let it (or its eager AI-client construction)
        # break the DD run.
        try:
            cls_svc = ClassificationService(self.db)
            classification = await cls_svc.get_vendor_classification(report.vendor_id)
            if classification and classification.final_label in (
                "financial_outsourcing", "it_outsourcing"
            ):
                report.outsourcing_checklist = (
                    "Additional outsourcing checks: SLA review, data residency, "
                    "sub-contractor disclosure, exit plan verification."
                )
        except Exception:  # AI adapter unavailable / no classification — non-fatal
            pass

        report.status = "ready"
        await self.db.flush()
        return report

    async def sign_off_report(self, report_id: uuid.UUID, user_id: uuid.UUID) -> DDReport:
        from datetime import datetime, timezone

        result = await self.db.execute(select(DDReport).where(DDReport.id == report_id))
        report = result.scalar_one()
        report.status = "signed_off"
        report.signed_off_by = user_id
        report.signed_off_at = datetime.now(timezone.utc)
        await self.audit_log.log("dd.signed_off", "dd_report", str(report.id), actor_id=user_id)
        await self.db.flush()
        return report
