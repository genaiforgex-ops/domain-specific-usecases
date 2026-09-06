"""Build Studio — autonomous feature-request / bug-fix pipeline.

State machine (auto-advanced based on time-in-state on every read):

  submitted    → analysing    (after 1s)
  analysing    → planning     (after 3s) — invokes CodingAgentService.analyse
  planning     → in_progress  (after 3s) — opens GitHub issue
  in_progress  → pr_open      (after 8s) — invokes implement(), creates PR
  pr_open      → (manual)     awaits human reviewer approval
  in_review    → merged       (after 1s) — merges PR
  merged       → deploying    (immediate)
  deploying    → deployed     (after 5s) — preview environment URL set

Failure terminals: rejected, failed.

The dwell-time values are intentionally short for a demonstrable scaffold;
production tunes them or replaces auto-advance with real callbacks from
GitHub webhooks + CI events.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.feature_request import FeatureRequest
from app.models.user import User
from app.schemas.feature_request import (
    FeatureRequestCreate,
    FeatureRequestOut,
    FeatureRequestSummary,
    FeatureRequestUpdate,
)
from app.services.agent_service import get_agent_service, get_github_service
from app.services.audit_service import write_audit


router = APIRouter(prefix="/api/build-studio", tags=["build-studio"])


# Dwell-time (seconds in a state before the engine advances).
_DWELL = {
    "submitted": 1,
    "analysing": 3,
    "planning": 3,
    "in_progress": 8,
    "in_review": 1,
    "merged": 0,
    "deploying": 5,
}


def _append_log(req: FeatureRequest, level: str, stage: str, message: str) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "stage": stage,
        "message": message,
    }
    log = list(req.agent_log or [])
    log.append(entry)
    req.agent_log = log


def _transition(req: FeatureRequest, new_status: str) -> None:
    req.status = new_status
    req.state_changed_at = datetime.now(timezone.utc)


def _advance_if_due(req: FeatureRequest) -> bool:
    """Move the request forward one state if its dwell-time has elapsed.

    Returns True if a transition happened (so the caller can commit).
    """
    if req.status in ("pr_open", "deployed", "failed", "rejected"):
        return False  # Terminal or awaiting human gate.
    now = datetime.now(timezone.utc)
    state_age = (now - req.state_changed_at).total_seconds()
    dwell = _DWELL.get(req.status, 0)
    if state_age < dwell:
        return False

    agent = get_agent_service()
    gh = get_github_service()

    if req.status == "submitted":
        _append_log(req, "info", "intake", f"Received {req.request_type}: \"{req.title[:120]}\"")
        _transition(req, "analysing")
        return True

    if req.status == "analysing":
        analysis = agent.analyse(req.title, req.description, req.request_type)
        req.plan = analysis.plan
        req.files_touched = analysis.files_touched
        req.loc_estimate = analysis.loc_estimate
        req.model_version = agent.model_version
        _append_log(req, "info", "analysis", "Analysing repository structure…")
        _append_log(req, "info", "analysis", analysis.summary)
        _append_log(
            req,
            "info",
            "analysis",
            f"Files in scope: {', '.join(analysis.files_touched[:4])}"
            + (f" (+{len(analysis.files_touched) - 4} more)" if len(analysis.files_touched) > 4 else ""),
        )
        _transition(req, "planning")
        return True

    if req.status == "planning":
        _append_log(req, "info", "plan", f"Plan ready — {len(req.plan or [])} step(s).")
        issue = gh.create_issue(
            title=req.title,
            body=req.description,
            labels=[req.request_type, req.priority],
            request_id=req.id,
        )
        req.github_issue_number = issue.number
        req.github_issue_url = issue.url
        _append_log(req, "info", "github", f"Opened tracking issue #{issue.number}")
        _transition(req, "in_progress")
        return True

    if req.status == "in_progress":
        impl = agent.implement(
            title=req.title,
            description=req.description,
            plan=req.plan or [],
            files_touched=req.files_touched or [],
            request_id=req.id,
        )
        req.branch_name = impl.branch_name
        req.diff_summary = impl.diff_summary
        _append_log(req, "info", "code", f"Drafting changes on branch {impl.branch_name}")
        _append_log(req, "info", "code", impl.diff_summary)
        if impl.tests_passed == impl.tests_total:
            _append_log(req, "success", "tests", f"Tests: {impl.tests_passed}/{impl.tests_total} passed")
        else:
            _append_log(req, "warn", "tests", f"Tests: {impl.tests_passed}/{impl.tests_total} passed — failing")
            _transition(req, "failed")
            return True
        pr = gh.open_pull_request(
            title=f"[{req.request_type}] {req.title[:120]}",
            body=f"Resolves #{req.github_issue_number}\n\n{req.description}\n\n---\n*Generated by LegalOS Build Studio*",
            branch=impl.branch_name,
            issue_number=req.github_issue_number,
            request_id=req.id,
        )
        req.pr_number = pr.number
        req.pr_url = pr.url
        req.pr_opened_at = datetime.now(timezone.utc)
        _append_log(req, "success", "github", f"Opened PR #{pr.number} — awaiting human review")
        _transition(req, "pr_open")
        return True

    if req.status == "in_review":
        sha = gh.merge_pull_request(req.pr_number or 0, req.id)
        _append_log(req, "success", "github", f"Merged PR #{req.pr_number} (sha {sha})")
        req.merged_at = datetime.now(timezone.utc)
        _transition(req, "merged")
        return True

    if req.status == "merged":
        _append_log(req, "info", "deploy", "Triggering deployment pipeline…")
        _transition(req, "deploying")
        return True

    if req.status == "deploying":
        depl = gh.trigger_deployment(req.pr_number or 0, req.id)
        req.deployment_url = depl.url
        req.deployed_at = datetime.now(timezone.utc)
        _append_log(req, "success", "deploy", f"Deployed to {depl.environment}: {depl.url}")
        _transition(req, "deployed")
        return True

    return False


def _advance_all_until_blocked(req: FeatureRequest) -> int:
    """Apply transitions repeatedly until no more are due (for the current
    instant). Bounded by a safety cap.
    """
    changes = 0
    for _ in range(10):
        if not _advance_if_due(req):
            break
        changes += 1
    return changes


@router.get("", response_model=list[FeatureRequestSummary])
def list_requests(
    user: User = Depends(require_permission(Permission.BUILD_REQUESTS)),
    db: Session = Depends(get_db),
) -> list[FeatureRequestSummary]:
    stmt = select(FeatureRequest).order_by(FeatureRequest.updated_at.desc())
    # Legal Admin / Super Admin see everyone's requests. Others see only their own.
    if user.role not in ("super_admin", "legal_admin"):
        stmt = stmt.where(FeatureRequest.created_by_id == user.id)
    rows = db.execute(stmt).scalars().all()
    any_changed = False
    for r in rows:
        if _advance_all_until_blocked(r) > 0:
            any_changed = True
    if any_changed:
        db.commit()
    return [FeatureRequestSummary.model_validate(r) for r in rows]


@router.post("", response_model=FeatureRequestOut, status_code=status.HTTP_201_CREATED)
def submit_request(
    payload: FeatureRequestCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.BUILD_REQUESTS)),
    db: Session = Depends(get_db),
) -> FeatureRequestOut:
    if payload.request_type not in ("bug", "feature", "enhancement", "refactor"):
        raise HTTPException(status_code=400, detail="Invalid request_type")
    agent = get_agent_service()
    label, score, rationale = agent.score_priority(
        payload.title, payload.description, payload.request_type
    )
    priority = payload.priority or label
    req = FeatureRequest(
        title=payload.title,
        description=payload.description,
        request_type=payload.request_type,
        priority=priority,
        priority_score=score,
        status="submitted",
        repository=payload.repository or "jfpsl/legalos",
        agent_log=[
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "stage": "intake",
                "message": f"Submitted by {user.full_name}. {rationale}",
            }
        ],
        model_version=agent.model_version,
        created_by_id=user.id,
    )
    db.add(req)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="build_request_submitted",
        module="build_studio",
        input_summary=f"{payload.request_type}: {payload.title[:200]}",
        ai_output_summary=rationale,
        confidence_score=score / 100,
        model_version=agent.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=req.id,
    )
    db.commit()
    db.refresh(req)
    return FeatureRequestOut.model_validate(req)


@router.get("/{req_id}", response_model=FeatureRequestOut)
def get_request(
    req_id: int,
    user: User = Depends(require_permission(Permission.BUILD_REQUESTS)),
    db: Session = Depends(get_db),
) -> FeatureRequestOut:
    req = db.get(FeatureRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if (
        req.created_by_id != user.id
        and user.role not in ("super_admin", "legal_admin")
    ):
        raise HTTPException(status_code=403, detail="Cannot view this request")
    if _advance_all_until_blocked(req) > 0:
        db.commit()
        db.refresh(req)
    return FeatureRequestOut.model_validate(req)


@router.post("/{req_id}/approve-pr", response_model=FeatureRequestOut)
def approve_pr(
    req_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.BUILD_PR_APPROVE)),
    db: Session = Depends(get_db),
) -> FeatureRequestOut:
    """Human gate — only Legal Admin / Super Admin can merge.

    Moves the request from pr_open into the in_review → merged → deploying →
    deployed automated tail.
    """
    req = db.get(FeatureRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pr_open":
        raise HTTPException(
            status_code=400, detail=f"Cannot approve from status '{req.status}'"
        )
    req.approved_by_id = user.id
    _append_log(req, "success", "review", f"PR approved by {user.full_name}")
    _transition(req, "in_review")
    write_audit(
        db,
        user=user,
        action_type="build_request_approved",
        module="build_studio",
        input_summary=f"PR #{req.pr_number} for request {req.id}",
        human_decision="approved",
        model_version=req.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=req.id,
    )
    # Run the merged + deploying transitions that are now due.
    _advance_all_until_blocked(req)
    db.commit()
    db.refresh(req)
    return FeatureRequestOut.model_validate(req)


@router.post("/{req_id}/reject", response_model=FeatureRequestOut)
def reject_request(
    req_id: int,
    request: Request,
    reason: str = "",
    user: User = Depends(require_permission(Permission.BUILD_PR_APPROVE)),
    db: Session = Depends(get_db),
) -> FeatureRequestOut:
    req = db.get(FeatureRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status in ("deployed", "merged", "deploying"):
        raise HTTPException(status_code=400, detail="Cannot reject a deployed request")
    _append_log(req, "warn", "review", f"Rejected by {user.full_name}: {reason or 'no reason given'}")
    _transition(req, "rejected")
    write_audit(
        db,
        user=user,
        action_type="build_request_rejected",
        module="build_studio",
        input_summary=req.title[:300],
        human_decision="rejected",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=req.id,
        extra={"reason": reason[:500]},
    )
    db.commit()
    db.refresh(req)
    return FeatureRequestOut.model_validate(req)


@router.patch("/{req_id}", response_model=FeatureRequestOut)
def update_request(
    req_id: int,
    payload: FeatureRequestUpdate,
    request: Request,
    user: User = Depends(require_permission(Permission.BUILD_REQUESTS)),
    db: Session = Depends(get_db),
) -> FeatureRequestOut:
    req = db.get(FeatureRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if (
        req.created_by_id != user.id
        and user.role not in ("super_admin", "legal_admin")
    ):
        raise HTTPException(status_code=403, detail="Cannot edit this request")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(req, field, value)
    write_audit(
        db,
        user=user,
        action_type="build_request_updated",
        module="build_studio",
        input_summary=payload.model_dump_json(exclude_unset=True)[:500],
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=req.id,
    )
    db.commit()
    db.refresh(req)
    return FeatureRequestOut.model_validate(req)
