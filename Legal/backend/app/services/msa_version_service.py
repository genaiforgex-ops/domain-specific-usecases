"""MSA/NDA version chain, diff, and negotiation task orchestration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.comparison import DocumentComparison
from app.models.msa import MSAEmail, MSATracker
from app.models.msa_version import MSADocumentVersion
from app.models.negotiation_task import NegotiationChangeTask
from app.models.playbook import PlaybookClause
from app.models.user import User
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.document_parser import DocumentParseError, parse_document
from app.services.document_storage import get_document_storage
from app.services.docx_structure_service import extract_structure
from app.services.suggestion_service import clause_to_suggestion_dict, filter_actionable_suggestions


def _severity_score(flag: str) -> float:
    f = (flag or "").lower()
    if f == "high":
        return 90.0
    if f == "medium":
        return 60.0
    if f == "low":
        return 30.0
    return 0.0


def risk_score_from_suggestions(suggestions: list[dict]) -> float:
    if not suggestions:
        return 0.0
    scores = [_severity_score(str(s.get("risk_flag") or "none")) for s in suggestions]
    return round(min(100.0, sum(scores) / max(1, len(scores))), 1)


def synthesize_suggestions_from_narrative(narrative: list[dict]) -> list[dict]:
    """Create reviewer-friendly suggestions when clause-level review yields none."""
    out: list[dict] = []
    for i, n in enumerate(narrative):
        old_text = (n.get("old_text") or "").strip()
        new_text = (n.get("new_text") or "").strip()
        excerpt = new_text or old_text or (n.get("title") or "Changed section")
        out.append(
            {
                "order_index": 50000 + i,
                "heading": n.get("title"),
                "clause_text": excerpt[:2000],
                "risk_flag": (n.get("severity") or "low").lower(),
                "confidence": 0.8,
                "rationale": n.get("impact") or "Change detected between legal and vendor versions.",
                "ai_suggestion": n.get("suggested_action") or "Review this change with legal owner.",
                "original_text": old_text or None,
                "proposed_text": new_text or None,
                "category": "legal_risk",
                "decision": "pending",
            }
        )
    return out


def _next_version_number(db: Session, tracker_id: int) -> int:
    current = db.scalar(
        select(func.max(MSADocumentVersion.version_number)).where(
            MSADocumentVersion.tracker_id == tracker_id
        )
    )
    return (current or 0) + 1


def _suggestions_from_review(result) -> list[dict]:
    return filter_actionable_suggestions(
        [clause_to_suggestion_dict(c) for c in result.clauses]
    )


def _is_docx_file(filename: str | None, mime_type: str | None) -> bool:
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    return name.endswith(".docx") or "wordprocessingml" in mime or "msword" in mime


def _extract_docx_structure(data: bytes, filename: str | None, mime_type: str | None):
    if not _is_docx_file(filename, mime_type):
        return None, None
    try:
        structure = extract_structure(data)
        return structure.to_dict(), structure.structure_hash
    except Exception:
        return None, None


def create_version(
    db: Session,
    tracker: MSATracker,
    *,
    source: str,
    extracted_text: str,
    user: User | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
    storage_key: str | None = None,
    sha256: str | None = None,
    parent_version_id: int | None = None,
    gmail_message_id: str | None = None,
    structure_snapshot: dict | None = None,
    structure_hash: str | None = None,
    run_compare: bool = True,
    ip_address: str | None = None,
    session_id: str | None = None,
) -> tuple[MSADocumentVersion, DocumentComparison | None]:
    vn = _next_version_number(db, tracker.id)
    version = MSADocumentVersion(
        tracker_id=tracker.id,
        version_number=vn,
        source=source,
        extracted_text=extracted_text,
        storage_key=storage_key,
        filename=filename,
        mime_type=mime_type,
        sha256=sha256,
        parent_version_id=parent_version_id,
        created_by_id=user.id if user else None,
        gmail_message_id=gmail_message_id,
        structure_snapshot=structure_snapshot,
        structure_hash=structure_hash,
    )
    db.add(version)
    db.flush()

    tracker.current_version = vn
    tracker.canonical_version_id = version.id
    if source == "legal_base":
        tracker.original_text = extracted_text
    elif source == "legal_redline":
        tracker.redlined_text = extracted_text

    comparison: DocumentComparison | None = None
    if run_compare and parent_version_id:
        parent = db.get(MSADocumentVersion, parent_version_id)
        if parent:
            comparison = _compare_and_task(
                db,
                tracker,
                parent,
                version,
                user,
                ip_address=ip_address,
                session_id=session_id,
            )
            version.comparison_id = comparison.id if comparison else None

    if source == "vendor_return":
        playbook = db.execute(
            select(PlaybookClause).where(
                PlaybookClause.contract_type.in_([tracker.contract_type, "ANY"])
            )
        ).scalars().all()
        user_id = user.id if user else None
        result = orch_tasks.review_contract(
            extracted_text,
            playbook,
            contract_type=tracker.contract_type,
            module="msa_automation",
            operation="vendor_review",
            user_id=user_id,
            db=db,
        )
        suggestions = _suggestions_from_review(result)
        if not suggestions and comparison and comparison.llm_narrative:
            suggestions = synthesize_suggestions_from_narrative(comparison.llm_narrative)
        tracker.ai_suggestions = suggestions
        tracker.risk_score = (
            risk_score_from_suggestions(suggestions) if suggestions else result.risk_score
        )
        tracker.status = "negotiation"
        if user:
            write_audit(
                db,
                user=user,
                action_type="msa_vendor_review",
                module="msa_automation",
                input_summary=f"tracker={tracker.id} v={vn}",
                ai_output_summary=f"risk={result.risk_score}",
                confidence_score=sum(c.confidence for c in result.clauses)
                / max(1, len(result.clauses)),
                model_version=result.model_version,
                ip_address=ip_address,
                session_id=session_id,
                target_id=tracker.id,
            )

    db.flush()
    return version, comparison


def _compare_and_task(
    db: Session,
    tracker: MSATracker,
    from_version: MSADocumentVersion,
    to_version: MSADocumentVersion,
    user: User | None,
    *,
    ip_address: str | None = None,
    session_id: str | None = None,
) -> DocumentComparison:
    user_id = user.id if user else None
    cmp_result = orch_tasks.compare_documents(
        from_version.extracted_text, to_version.extracted_text
    )
    narrative = orch_tasks.summarize_document_changes(
        from_version.extracted_text,
        to_version.extracted_text,
        cmp_result.diff_blocks,
        cmp_result.risk_commentary,
        contract_type=tracker.contract_type,
        module="msa_automation",
        operation="compare_documents",
        user_id=user_id,
        db=db,
    )
    llm_json = [
        {
            "diff_index": c.diff_index,
            "title": c.title,
            "old_text": c.old_text,
            "new_text": c.new_text,
            "severity": c.severity,
            "impact": c.impact,
            "suggested_action": c.suggested_action,
            "clause_ref": c.clause_ref,
            "change_summary": c.change_summary,
            "rationale": c.rationale,
        }
        for c in narrative.changes
    ]
    label = f"{tracker.vendor_name} v{from_version.version_number}→v{to_version.version_number}"
    comparison = DocumentComparison(
        label=label,
        v1_filename=from_version.filename or f"v{from_version.version_number}",
        v2_filename=to_version.filename or f"v{to_version.version_number}",
        v1_text=from_version.extracted_text,
        v2_text=to_version.extracted_text,
        diff_blocks=[asdict(b) for b in cmp_result.diff_blocks],
        risk_commentary=[asdict(f) for f in cmp_result.risk_commentary],
        summary_report=cmp_result.summary_report,
        llm_narrative=llm_json,
        tracker_id=tracker.id,
        from_version_id=from_version.id,
        to_version_id=to_version.id,
        model_version=cmp_result.model_version,
        created_by_id=user.id if user else 1,
    )
    db.add(comparison)
    db.flush()

    now = datetime.now(timezone.utc)
    for item in narrative.changes:
        sev = (item.severity or "medium").lower()
        if sev == "low":
            continue
        clause_ref = item.clause_ref or ""
        title = f"{sev.upper()}: {clause_ref} — {item.title}" if clause_ref else f"{sev.upper()}: {item.title}"
        description = item.impact or ""
        if item.suggested_action:
            description = f"{description}\n\nWhy it matters: {item.suggested_action}".strip()
        due = now + timedelta(days=2 if sev == "high" else 5)
        existing = db.execute(
            select(NegotiationChangeTask).where(
                NegotiationChangeTask.tracker_id == tracker.id,
                NegotiationChangeTask.status == "open",
                NegotiationChangeTask.title == title,
            )
        ).scalar_one_or_none()
        if existing:
            existing.description = description
            existing.suggested_action = item.suggested_action
            existing.severity = sev
            existing.version_id = to_version.id
            existing.comparison_id = comparison.id
            existing.due_date = due
            continue
        db.add(
            NegotiationChangeTask(
                tracker_id=tracker.id,
                version_id=to_version.id,
                comparison_id=comparison.id,
                diff_index=item.diff_index if item.diff_index >= 0 else None,
                clause_ref=clause_ref or None,
                title=title[:512],
                description=description,
                suggested_action=item.suggested_action,
                severity=sev,
                status="open",
                assigned_to_id=tracker.assigned_to_id,
                due_date=due,
            )
        )

    if user:
        write_audit(
            db,
            user=user,
            action_type="msa_diff_generated",
            module="msa_automation",
            input_summary=label,
            ai_output_summary=narrative.executive_summary,
            model_version=narrative.model_version,
            ip_address=ip_address,
            session_id=session_id,
            target_id=tracker.id,
            extra={"comparison_id": comparison.id, "tasks": len(narrative.changes)},
        )
    return comparison


def ingest_file_version(
    db: Session,
    tracker: MSATracker,
    data: bytes,
    filename: str,
    mime_type: str | None,
    source: str,
    user: User,
    parent_version_id: int | None = None,
    gmail_message_id: str | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
) -> tuple[MSADocumentVersion, DocumentComparison | None]:
    text = parse_document(data, filename, mime_type)
    storage = get_document_storage()
    storage_key, sha = storage.upload(data, filename, mime_type or "application/octet-stream")
    structure_snapshot, structure_hash = _extract_docx_structure(data, filename, mime_type)
    # Always diff against the immediately preceding version (v_n vs v_{n-1}),
    # so V3 is compared with V2 regardless of who created V2.
    if parent_version_id is None:
        parent_version_id = _latest_version_id(db, tracker.id)
    return create_version(
        db,
        tracker,
        source=source,
        extracted_text=text,
        user=user,
        filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        sha256=sha,
        parent_version_id=parent_version_id,
        gmail_message_id=gmail_message_id,
        structure_snapshot=structure_snapshot,
        structure_hash=structure_hash,
        ip_address=ip_address,
        session_id=session_id,
    )


def _last_legal_sent_version_id(db: Session, tracker_id: int) -> int | None:
    row = db.execute(
        select(MSADocumentVersion)
        .where(
            MSADocumentVersion.tracker_id == tracker_id,
            MSADocumentVersion.source.in_(["legal_redline", "legal_base"]),
        )
        .order_by(MSADocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row.id if row else None


def _latest_version_id(db: Session, tracker_id: int) -> int | None:
    row = db.execute(
        select(MSADocumentVersion)
        .where(MSADocumentVersion.tracker_id == tracker_id)
        .order_by(MSADocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row.id if row else None


def compare_two_versions(
    db: Session,
    tracker: MSATracker,
    from_version: MSADocumentVersion,
    to_version: MSADocumentVersion,
    user: User | None,
) -> DocumentComparison:
    """Run an on-demand comparison between any two existing versions.
    Returns the persisted DocumentComparison row (so it appears in /changes).
    """
    return _compare_and_task(db, tracker, from_version, to_version, user)


def get_latest_changes(db: Session, tracker_id: int) -> DocumentComparison | None:
    return db.execute(
        select(DocumentComparison)
        .where(DocumentComparison.tracker_id == tracker_id)
        .order_by(DocumentComparison.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
