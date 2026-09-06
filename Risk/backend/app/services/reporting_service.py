import io
import uuid
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.classification import ClassificationJob
from app.models.vendor import DDReport, Vendor


def _label(value) -> str:
    """Human-readable form of a snake_case classification label."""
    if not value:
        return "—"
    return escape(str(value).replace("_", " ").title())


def _s(value) -> str:
    """Coerce a value (str or dict) to safe display text for a PDF paragraph."""
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = [str(v) for v in value.values() if v not in (None, "", [], {})]
        return escape(" · ".join(parts))
    return escape(str(value))


class ReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_dd_pdf(self, report_id: uuid.UUID) -> bytes:
        result = await self.db.execute(
            select(DDReport)
            .options(selectinload(DDReport.findings), selectinload(DDReport.vendor))
            .where(DDReport.id == report_id)
        )
        report = result.scalar_one()
        vendor: Vendor = report.vendor
        audit: dict = report.audit_data or {}
        risk: dict = audit.get("risk") or {}

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"DD Report — {vendor.legal_name}")
        styles = getSampleStyleSheet()
        h2, normal = styles["Heading2"], styles["Normal"]

        story = [
            Paragraph(f"<b>Vendor Due Diligence Report</b>", styles["Title"]),
            Paragraph(_s(vendor.legal_name), styles["Heading1"]),
            Spacer(1, 8),
        ]

        # --- Verdict summary ---
        rating = _s(risk.get("rating")) or "—"
        decision = _s(risk.get("decision")) or "—"
        score = report.red_flag_score if report.red_flag_score is not None else risk.get("score", "N/A")
        story += [
            Paragraph(f"<b>Recommendation:</b> {decision}", normal),
            Paragraph(f"<b>Risk score:</b> {score}/100 ({rating})", normal),
            Paragraph(f"<b>Report status:</b> {_s(report.status)}", normal),
        ]
        if audit.get("industry"):
            story.append(Paragraph(f"<b>Industry:</b> {_s(audit.get('industry'))}", normal))
        if vendor.website:
            story.append(Paragraph(f"<b>Website:</b> {_s(vendor.website)}", normal))
        story.append(Paragraph(f"<b>CIN:</b> {_s(vendor.cin) or 'N/A'} &nbsp; <b>PAN:</b> {_s(vendor.pan) or 'N/A'}", normal))

        if audit.get("business_description"):
            story += [Spacer(1, 6), Paragraph(_s(audit.get("business_description")), normal)]
        if risk.get("summary"):
            story += [Spacer(1, 8), Paragraph("<b>Summary</b>", h2), Paragraph(_s(risk.get("summary")), normal)]

        def bullet_section(title: str, items, formatter=_s):
            items = items or []
            if not items:
                return
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"<b>{escape(title)}</b>", h2))
            story.append(ListFlowable(
                [ListItem(Paragraph(formatter(i), normal), leftIndent=10) for i in items],
                bulletType="bullet", start="•",
            ))

        # --- Flags & conditions ---
        bullet_section("Red flags", risk.get("red_flags"))
        bullet_section("Green flags", risk.get("green_flags"))
        bullet_section("Conditions for approval", risk.get("conditions"))

        # --- Score factors ---
        def fmt_factor(f):
            if isinstance(f, dict):
                label = " — ".join(str(x) for x in [f.get("factor"), f.get("detail")] if x)
                return escape(label or "Factor")
            return _s(f)
        bullet_section("How this score was reached", risk.get("factors"), fmt_factor)

        # --- Legal ---
        legal = audit.get("legal") or {}

        def fmt_lit(l):
            if isinstance(l, dict):
                head = " · ".join(str(x) for x in [l.get("type"), l.get("status"), l.get("case_number"), l.get("court")] if x)
                return f"<b>{escape(head or 'Litigation')}</b><br/>{escape(str(l.get('summary') or ''))}"
            return _s(l)

        def fmt_news(n):
            if isinstance(n, dict):
                head = " · ".join(str(x) for x in [n.get("headline"), n.get("source"), n.get("date")] if x)
                return f"<b>{escape(head or 'News')}</b><br/>{escape(str(n.get('summary') or ''))}"
            return _s(n)

        bullet_section("Litigation", legal.get("litigations"), fmt_lit)
        bullet_section("Adverse & general news", legal.get("news"), fmt_news)

        # --- Compliance checks ---
        checks = audit.get("compliance_checks") or {}
        if checks:
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Compliance checks</b>", h2))
            rows = []
            for name, c in checks.items():
                status = c.get("status", "") if isinstance(c, dict) else str(c)
                detail = c.get("details", "") if isinstance(c, dict) else ""
                reg = c.get("registration_id") if isinstance(c, dict) else None
                line = f"<b>{escape(name.replace('_', ' ').title())}:</b> {escape(str(status))}"
                if detail:
                    line += f" — {escape(str(detail))}"
                if reg:
                    line += f" [{escape(str(c.get('registration_type') or 'ID'))}: {escape(str(reg))}]"
                rows.append(ListItem(Paragraph(line, normal), leftIndent=10))
            story.append(ListFlowable(rows, bulletType="bullet", start="•"))

        # --- Social & online reputation ---
        social = audit.get("social") or {}
        if social.get("reputation") or social.get("review_summary") or social.get("profiles"):
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Social &amp; online reputation</b>", h2))
            if social.get("reputation"):
                story.append(Paragraph(f"<b>Reputation:</b> {_s(social.get('reputation'))}", normal))
            if social.get("review_summary"):
                story.append(Paragraph(_s(social.get("review_summary")), normal))

            def fmt_profile(p):
                if isinstance(p, dict):
                    return escape(" · ".join(str(x) for x in [p.get("platform"), p.get("handle"), p.get("url"), p.get("followers")] if x))
                return _s(p)
            bullet_section("Social profiles", social.get("profiles"), fmt_profile)

        # --- Derived findings (evidence list) ---
        if report.findings:
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Screening findings</b>", h2))
            for f in report.findings:
                story.append(Paragraph(
                    f"<b>[{escape(f.category)}]</b> {escape(f.title)} ({escape(f.source_tier)})<br/>{escape(f.summary or '')}",
                    normal,
                ))
                if f.source_url:
                    story.append(Paragraph(f'<font color="blue">{escape(f.source_url)}</font>', normal))
                story.append(Spacer(1, 6))

        if report.outsourcing_checklist:
            story += [Spacer(1, 10), Paragraph("<b>Outsourcing checklist (M1 linked)</b>", h2),
                      Paragraph(_s(report.outsourcing_checklist), normal)]

        # --- Sources ---
        sources = audit.get("_grounding_sources") or []
        if sources:
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"<b>Grounded sources ({len(sources)})</b>", h2))
            for src in sources[:30]:
                url = src.get("url") if isinstance(src, dict) else str(src)
                title = (src.get("title") if isinstance(src, dict) else "") or url
                story.append(Paragraph(f'• <font color="blue">{escape(str(title))}</font> — {escape(str(url))}', styles["Italic"]))

        story.append(Spacer(1, 14))
        story.append(Paragraph(
            f"<i>Generated by GenAIForge Risk · model: {escape(str(audit.get('_model_version') or 'n/a'))} · "
            f"weights: {escape(str(report.weights_version or 'n/a'))}</i>",
            styles["Italic"],
        ))

        doc.build(story)
        return buffer.getvalue()

    async def generate_classification_pdf(self, job_id: uuid.UUID) -> bytes:
        """Report for a single M1 outsourcing classification: the confirmed
        outcome plus both regulators' AI suggestions, reasoning and cited
        clauses. Raises ValueError if the job doesn't exist."""
        result = await self.db.execute(
            select(ClassificationJob)
            .options(
                selectinload(ClassificationJob.vendor),
                selectinload(ClassificationJob.document),
            )
            .where(ClassificationJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("Classification not found")

        vendor: Vendor = job.vendor

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer, pagesize=A4, title=f"Classification — {vendor.legal_name}"
        )
        styles = getSampleStyleSheet()
        h2, normal = styles["Heading2"], styles["Normal"]

        story = [
            Paragraph("<b>Outsourcing Risk Classification</b>", styles["Title"]),
            Paragraph(_s(vendor.legal_name), styles["Heading1"]),
            Spacer(1, 8),
            Paragraph(f"<b>Final label:</b> {_label(job.final_label)}", normal),
            Paragraph(f"<b>Status:</b> {_s(job.status)}", normal),
        ]
        if job.created_at:
            story.append(
                Paragraph(f"<b>Submitted:</b> {job.created_at:%Y-%m-%d %H:%M}", normal)
            )
        if job.document_filename:
            story.append(
                Paragraph(f"<b>Source document:</b> {_s(job.document_filename)}", normal)
            )
        if job.clause_library_version:
            story.append(
                Paragraph(
                    f"<b>Clause library version:</b> {_s(job.clause_library_version)}",
                    normal,
                )
            )

        def regulator_section(name: str, label, confidence, evidence: dict | None):
            evidence = evidence or {}
            if not label and not evidence:
                return
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"<b>{escape(name)} suggestion</b>", h2))
            conf = f"{round(confidence * 100)}%" if confidence is not None else "—"
            story.append(
                Paragraph(f"<b>Label:</b> {_label(label)} &nbsp; <b>Confidence:</b> {conf}", normal)
            )
            if evidence.get("reasoning"):
                story.append(Paragraph(_s(evidence.get("reasoning")), normal))
            cited = [
                e for e in (evidence.get("evidence") or [])
                if isinstance(e, dict) and (e.get("clause_ref") or e.get("clause_text"))
            ]
            if cited:
                story.append(ListFlowable(
                    [
                        ListItem(
                            Paragraph(
                                f"<b>{escape(str(e.get('clause_ref') or 'Clause'))}</b>"
                                + (f"<br/>{escape(str(e.get('clause_text'))[:400])}" if e.get("clause_text") else ""),
                                normal,
                            ),
                            leftIndent=10,
                        )
                        for e in cited
                    ],
                    bulletType="bullet", start="•",
                ))

        regulator_section("RBI", job.rbi_label, job.rbi_confidence, job.rbi_evidence)
        regulator_section("SEBI", job.sebi_label, job.sebi_confidence, job.sebi_evidence)

        if job.justification:
            story += [
                Spacer(1, 10),
                Paragraph("<b>Reviewer justification</b>", h2),
                Paragraph(_s(job.justification), normal),
            ]

        if job.input_text:
            story += [
                Spacer(1, 10),
                Paragraph("<b>Assessment text</b>", h2),
                Paragraph(_s(job.input_text[:4000]), normal),
            ]

        story += [
            Spacer(1, 14),
            Paragraph("<i>Generated by GenAIForge Risk · M1 Outsourcing Classification</i>", styles["Italic"]),
        ]

        pdf.build(story)
        return buffer.getvalue()
