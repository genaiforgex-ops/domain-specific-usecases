import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.factory import get_email_adapter
from app.audit.service import AuditService
from app.core.config import get_settings
from app.models.classification import ClassificationJob
from app.models.form import FormAssignment, FormSubmission, FormTemplate
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.services.classification_service import ClassificationService
from app.services.email_templates import form_assigned, form_reminder
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

VENDOR_NAME_LABELS = ("name of the service provider",)
VENDOR_WEBSITE_LABELS = ("website link of the service provider",)


class FormService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    async def list_templates(self) -> list[FormTemplate]:
        result = await self.db.execute(
            select(FormTemplate).order_by(FormTemplate.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_template(self, template_id: uuid.UUID) -> FormTemplate | None:
        result = await self.db.execute(select(FormTemplate).where(FormTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def create_template(self, name: str, schema: dict, created_by: uuid.UUID | None) -> FormTemplate:
        await self.db.execute(
            select(FormTemplate).where(FormTemplate.is_active.is_(True))
        )
        # Deactivate other templates when creating a new active one
        active = await self.db.execute(select(FormTemplate).where(FormTemplate.is_active.is_(True)))
        for t in active.scalars().all():
            t.is_active = False

        template = FormTemplate(name=name, schema=schema, is_active=True, created_by=created_by, version=1)
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def update_template(
        self, template: FormTemplate, *, name: str | None = None, schema: dict | None = None, is_active: bool | None = None
    ) -> FormTemplate:
        if name is not None:
            template.name = name
        if schema is not None:
            template.schema = schema
            template.version += 1
        if is_active is not None:
            template.is_active = is_active
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def list_assignments(self, *, assignee_id: uuid.UUID | None = None) -> list[FormAssignment]:
        q = select(FormAssignment).options(
            selectinload(FormAssignment.template),
            selectinload(FormAssignment.submission),
        )
        if assignee_id:
            q = q.where(FormAssignment.assignee_id == assignee_id)
        q = q.order_by(FormAssignment.created_at.desc())
        result = await self.db.execute(q)
        assignments = list(result.scalars().all())
        await self._enrich_assignments(assignments)
        return assignments

    async def get_assignment(self, assignment_id: uuid.UUID) -> FormAssignment | None:
        result = await self.db.execute(
            select(FormAssignment)
            .options(selectinload(FormAssignment.template), selectinload(FormAssignment.submission))
            .where(FormAssignment.id == assignment_id)
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            await self._enrich_assignments([assignment])
            self._apply_vendor_prefill(assignment)
        return assignment

    async def _enrich_assignments(self, assignments: list[FormAssignment]) -> None:
        if not assignments:
            return
        vendor_ids = {a.vendor_id for a in assignments if a.vendor_id}
        assignee_ids = {a.assignee_id for a in assignments}
        job_ids = {a.classification_job_id for a in assignments if a.classification_job_id}
        vendors: dict[uuid.UUID, Vendor] = {}
        users: dict[uuid.UUID, User] = {}
        jobs: dict[uuid.UUID, tuple[str, str | None]] = {}
        if vendor_ids:
            vr = await self.db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
            vendors = {v.id: v for v in vr.scalars().all()}
        if assignee_ids:
            ur = await self.db.execute(select(User).where(User.id.in_(assignee_ids)))
            users = {u.id: u for u in ur.scalars().all()}
        if job_ids:
            # One query for the whole list, so the caller can show how each
            # submitted form's background classification is getting on without
            # polling the classification endpoint once per row.
            jr = await self.db.execute(
                select(
                    ClassificationJob.id,
                    ClassificationJob.status,
                    ClassificationJob.final_label,
                ).where(ClassificationJob.id.in_(job_ids))
            )
            jobs = {row[0]: (row[1], row[2]) for row in jr.all()}
        for a in assignments:
            if a.vendor_id and a.vendor_id in vendors:
                a._vendor = vendors[a.vendor_id]  # type: ignore[attr-defined]
            if a.assignee_id in users:
                a._assignee = users[a.assignee_id]  # type: ignore[attr-defined]
            job = jobs.get(a.classification_job_id) if a.classification_job_id else None
            if job:
                a._classification_status, a._classification_label = job  # type: ignore[attr-defined]

    def _vendor_name_field_id(self, schema: dict) -> str | None:
        for field in self._iter_fields(schema):
            label = (field.get("label") or "").lower()
            if any(k in label for k in VENDOR_NAME_LABELS):
                return field["id"]
        return None

    def _apply_vendor_prefill(self, assignment: FormAssignment) -> None:
        vendor = getattr(assignment, "_vendor", None)
        if not vendor or not assignment.template:
            return
        field_id = self._vendor_name_field_id(assignment.template.schema)
        if not field_id:
            return
        draft = dict(assignment.draft_answers or {})
        if not draft.get(field_id):
            draft[field_id] = vendor.legal_name
            assignment.draft_answers = draft

    async def _resolve_vendor(
        self,
        *,
        vendor_id: uuid.UUID | None,
        vendor_name: str | None,
    ) -> Vendor:
        if vendor_id:
            result = await self.db.execute(select(Vendor).where(Vendor.id == vendor_id))
            vendor = result.scalar_one_or_none()
            if not vendor:
                raise ValueError("Vendor not found")
            return vendor
        name = (vendor_name or "").strip()
        if not name:
            raise ValueError("Either vendor_id or vendor_name is required")
        result = await self.db.execute(select(Vendor).where(Vendor.legal_name == name))
        vendor = result.scalar_one_or_none()
        if vendor:
            return vendor
        vendor = Vendor(legal_name=name, country="IN")
        self.db.add(vendor)
        await self.db.flush()
        await self.db.refresh(vendor)
        return vendor

    async def create_assignment(
        self,
        *,
        template_id: uuid.UUID,
        assignee_id: uuid.UUID,
        assigned_by_id: uuid.UUID,
        title: str,
        due_at: datetime | None,
        vendor_id: uuid.UUID | None,
        vendor_name: str | None = None,
    ) -> FormAssignment:
        template = await self.get_template(template_id)
        if not template:
            raise ValueError("Template not found")

        vendor = await self._resolve_vendor(vendor_id=vendor_id, vendor_name=vendor_name)

        assignment = FormAssignment(
            template_id=template_id,
            assignee_id=assignee_id,
            assigned_by_id=assigned_by_id,
            title=title,
            due_at=due_at,
            vendor_id=vendor.id,
            status="assigned",
        )
        self.db.add(assignment)
        await self.db.flush()
        await self.db.refresh(assignment, ["template"])

        await self._notify_assignment_created(assignment, vendor)
        return assignment

    async def create_assignments_bulk(
        self,
        *,
        template_id: uuid.UUID,
        assigned_by_id: uuid.UUID,
        title: str,
        due_at: datetime | None,
        items: list,
    ) -> list[FormAssignment]:
        template = await self.get_template(template_id)
        if not template:
            raise ValueError("Template not found")

        created: list[FormAssignment] = []
        for item in items:
            vendor = await self._resolve_vendor(
                vendor_id=getattr(item, "vendor_id", None),
                vendor_name=getattr(item, "vendor_name", None),
            )
            row_title = f"{title} — {vendor.legal_name}"
            assignment = FormAssignment(
                template_id=template_id,
                assignee_id=item.assignee_id,
                assigned_by_id=assigned_by_id,
                title=row_title,
                due_at=due_at,
                vendor_id=vendor.id,
                status="assigned",
            )
            self.db.add(assignment)
            await self.db.flush()
            await self.db.refresh(assignment, ["template"])
            await self._notify_assignment_created(assignment, vendor)
            created.append(assignment)
        return created

    async def _notify_assignment_created(self, assignment: FormAssignment, vendor: Vendor) -> None:
        # In-app notification keeps the relative link: it is rendered inside the
        # SPA, which already knows its own origin. The email needs an absolute one.
        await self.notifications.notify(
            assignment.assignee_id,
            title="New form assigned",
            body=(
                f'You have been assigned "{assignment.title}" for vendor {vendor.legal_name}. '
                "Please complete it before the due date."
            ),
            link=f"/my-forms/{assignment.id}",
            send_email=False,
        )
        assignee_email = await self._get_user_email(assignment.assignee_id)
        if not assignee_email:
            logger.warning(
                "Assignment %s: assignee %s has no email address; skipping mail",
                assignment.id,
                assignment.assignee_id,
            )
            return
        subject, text, html = form_assigned(
            title=assignment.title,
            vendor_name=vendor.legal_name,
            due_at=assignment.due_at,
            url=self._form_url(assignment.id),
        )
        await self._send_mail_safe(
            [assignee_email],
            subject=subject,
            text=text,
            html=html,
            cc=await self._cc_admins(exclude=assignee_email),
        )

    async def save_draft(self, assignment: FormAssignment, answers: dict) -> FormAssignment:
        if assignment.status == "submitted":
            raise ValueError("Assignment already submitted")
        assignment.draft_answers = answers
        assignment.status = "in_progress"
        assignment.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return assignment

    def _iter_fields(self, schema: dict):
        for section in schema.get("sections") or []:
            for field in section.get("fields") or []:
                yield field
        for group in schema.get("repeatable_groups") or []:
            for field in group.get("fields") or []:
                yield field

    def _validate_answers(self, schema: dict, answers: dict) -> None:
        missing: list[str] = []
        for field in self._iter_fields(schema):
            if not field.get("required"):
                continue
            val = answers.get(field["id"])
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(field.get("label") or field["id"])
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing[:5])}")

    def _serialize_answers(self, schema: dict, answers: dict) -> str:
        lines: list[str] = []
        field_labels = {f["id"]: f.get("label", f["id"]) for f in self._iter_fields(schema)}
        for field_id, label in field_labels.items():
            val = answers.get(field_id)
            if val is None or val == "":
                continue
            if isinstance(val, list):
                for i, row in enumerate(val, 1):
                    for k, v in row.items():
                        if v:
                            sub_label = field_labels.get(k, k)
                            lines.append(f"{label} (row {i}) — {sub_label}: {v}")
            else:
                lines.append(f"{label}: {val}")
        return "\n".join(lines)

    def _extract_vendor_info(self, schema: dict, answers: dict) -> tuple[str | None, str | None]:
        name = website = None
        for field in self._iter_fields(schema):
            label = (field.get("label") or "").lower()
            val = answers.get(field["id"])
            if not isinstance(val, str) or not val.strip():
                continue
            if any(k in label for k in VENDOR_NAME_LABELS):
                name = val.strip()
            if any(k in label for k in VENDOR_WEBSITE_LABELS):
                website = val.strip()
        return name, website

    async def _find_or_create_vendor(self, schema: dict, answers: dict) -> Vendor:
        legal_name, website = self._extract_vendor_info(schema, answers)
        if not legal_name:
            legal_name = "Unknown Vendor"
        result = await self.db.execute(select(Vendor).where(Vendor.legal_name == legal_name))
        vendor = result.scalar_one_or_none()
        if vendor:
            if website and not vendor.website:
                vendor.website = website
            return vendor
        vendor = Vendor(legal_name=legal_name, website=website, country="IN")
        self.db.add(vendor)
        await self.db.flush()
        await self.db.refresh(vendor)
        return vendor

    async def _get_vendor_for_submit(
        self,
        assignment: FormAssignment,
        schema: dict,
        answers: dict,
    ) -> Vendor:
        legal_name, website = self._extract_vendor_info(schema, answers)
        if assignment.vendor_id:
            result = await self.db.execute(select(Vendor).where(Vendor.id == assignment.vendor_id))
            vendor = result.scalar_one_or_none()
            if vendor:
                if legal_name and legal_name != vendor.legal_name:
                    vendor.legal_name = legal_name
                if website and not vendor.website:
                    vendor.website = website
                await self.db.flush()
                return vendor
        return await self._find_or_create_vendor(schema, answers)

    async def submit_assignment(
        self,
        assignment: FormAssignment,
        answers: dict,
        submitter_id: uuid.UUID,
    ) -> tuple[FormSubmission, uuid.UUID]:
        if assignment.status == "submitted":
            raise ValueError("Assignment already submitted")
        schema = assignment.template.schema if assignment.template else {}
        self._validate_answers(schema, answers)

        vendor = await self._get_vendor_for_submit(assignment, schema, answers)
        assignment.vendor_id = vendor.id
        text = self._serialize_answers(schema, answers)

        submission = FormSubmission(
            assignment_id=assignment.id,
            answers=answers,
            submitted_by=submitter_id,
        )
        self.db.add(submission)

        classification = ClassificationService(self.db)
        job = await classification.create_job(
            vendor_id=vendor.id,
            text=text,
            document_id=None,
            created_by=submitter_id,
        )

        assignment.status = "submitted"
        assignment.draft_answers = answers
        assignment.classification_job_id = job.id
        assignment.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self.audit.log(
            event_type="form.submitted",
            entity_type="form_assignment",
            entity_id=str(assignment.id),
            actor_id=submitter_id,
            payload={"classification_job_id": str(job.id), "vendor_id": str(vendor.id)},
        )

        assignee = getattr(assignment, "_assignee", None)
        assignee_label = (
            (assignee.display_name or assignee.email) if assignee else "A user"
        )
        await self.notifications.notify_admins(
            title="Form submitted for classification",
            body=(
                f'"{assignment.title}" was submitted by {assignee_label} '
                f"for vendor {vendor.legal_name}. Classification has started."
            ),
            link=f"/m1?job={job.id}",
        )

        return submission, job.id

    async def send_reminder(self, assignment: FormAssignment) -> None:
        if assignment.status == "submitted":
            raise ValueError("Cannot remind on a submitted assignment")
        await self.notifications.notify(
            assignment.assignee_id,
            title="Form reminder",
            body=f'Reminder: please complete "{assignment.title}".',
            link=f"/my-forms/{assignment.id}",
            send_email=False,
        )
        email_addr = await self._get_user_email(assignment.assignee_id)
        if email_addr:
            vendor_name = await self._vendor_name(assignment.vendor_id)
            subject, text, html = form_reminder(
                title=assignment.title,
                vendor_name=vendor_name,
                due_at=assignment.due_at,
                url=self._form_url(assignment.id),
            )
            await self._send_mail_safe(
                [email_addr],
                subject=subject,
                text=text,
                html=html,
                cc=await self._cc_admins(exclude=email_addr),
            )
        else:
            logger.warning(
                "Assignment %s: assignee %s has no email address; skipping reminder mail",
                assignment.id,
                assignment.assignee_id,
            )
        # Stamped even when the mail failed. The scheduler uses this as a
        # rate-limit, and retrying a broken SMTP config every 24h is preferable
        # to hammering it on every sweep.
        assignment.last_reminder_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _get_user_email(self, user_id: uuid.UUID) -> str | None:
        result = await self.db.execute(select(User.email).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _admin_emails(self) -> list[str]:
        result = await self.db.execute(
            select(User.email)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role == "admin", User.is_active.is_(True))
        )
        return [row[0] for row in result.all()]

    async def _cc_admins(self, *, exclude: str | None = None) -> list[str]:
        """Admin addresses for the Cc line, minus `exclude`.

        An admin can also be the assignee, and appearing in both To and Cc makes
        the mail look duplicated and can trip spam heuristics.
        """
        skip = (exclude or "").strip().lower()
        return [e for e in await self._admin_emails() if e and e.strip().lower() != skip]

    async def _vendor_name(self, vendor_id: uuid.UUID | None) -> str:
        if not vendor_id:
            return "—"
        result = await self.db.execute(select(Vendor.legal_name).where(Vendor.id == vendor_id))
        return result.scalar_one_or_none() or "—"

    def _form_url(self, assignment_id: uuid.UUID) -> str:
        """Absolute URL to the fill page, for use in email.

        Not the same as auth.py's _frontend_url, which intentionally returns a
        bare path when frontend_base_url is blank — correct for a browser
        redirect, useless in an inbox. frontend_base_url IS blank in deployed
        environments (one ingress serves both), so public_base_url is the
        fallback that actually holds an origin there.
        """
        settings = get_settings()
        base = (settings.frontend_base_url or settings.public_base_url).rstrip("/")
        path = f"/my-forms/{assignment_id}"
        if not base:
            logger.warning(
                "Neither FRONTEND_BASE_URL nor PUBLIC_BASE_URL is set — the form "
                "link in this email will be a relative path and will not open."
            )
        return f"{base}{path}" if base else path

    async def _send_mail_safe(
        self,
        to: list[str],
        *,
        subject: str,
        text: str,
        html: str | None = None,
        cc: list[str] | None = None,
    ) -> None:
        """Send mail without ever letting a failure reach the caller.

        Both call sites run inside the request transaction, before the endpoint
        commits. Letting an SMTP error propagate would 500 the request and roll
        back the assignment — losing the form because the notification about it
        failed. The mail is the less important half; it degrades, the write does
        not.
        """
        try:
            adapter = get_email_adapter()
            msg_id = await adapter.send(to, subject, text, cc=cc, html=html)
            logger.info("Form email sent to=%s cc=%s id=%s", to, cc or [], msg_id)
        except Exception:
            logger.exception("Form email FAILED to=%s cc=%s subject=%s", to, cc or [], subject)

    async def delete_assignment(self, assignment_id: uuid.UUID) -> None:
        assignment = await self.get_assignment(assignment_id)
        if not assignment:
            raise ValueError("Assignment not found")
        if assignment.submission:
            await self.db.delete(assignment.submission)
        await self.db.delete(assignment)
        await self.db.flush()

    async def delete_template(self, template_id: uuid.UUID) -> None:
        template = await self.get_template(template_id)
        if not template:
            raise ValueError("Template not found")
        result = await self.db.execute(
            select(FormAssignment)
            .options(selectinload(FormAssignment.submission))
            .where(FormAssignment.template_id == template_id)
        )
        for assignment in result.scalars().all():
            if assignment.submission:
                await self.db.delete(assignment.submission)
            await self.db.delete(assignment)
        await self.db.delete(template)
        await self.db.flush()
