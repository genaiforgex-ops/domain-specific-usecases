"""Replace placeholder regulator clauses with sourced RBI/SEBI text

Revision ID: 003
Revises: 002
Create Date: 2026-06-18

Sourced from RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025
[RBI/DOR/2025-26/363]; RBI (Outsourcing of IT Services) Directions, 2023;
and SEBI Master Circular for Investment Advisers, Section 12. Pulled from
secondary republications (TaxGuru, Vinod Kothari Consultants) - NOT verified
against the gazetted original. Compliance must verify before this is relied
on for a real classification decision.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

OLD_PLACEHOLDER_REFS = [
    "RBI-OS-001", "RBI-OS-002", "RBI-IT-001", "SEBI-OS-001", "RBI-GEN-001",
]

CLAUSES = [
    (
        "RBI", "RBI-OUT-2025-S6.1", "financial",
        '[RBI NBFC Managing Risks in Outsourcing Directions, 2025 - Para 6(1)] '
        '"Outsourcing" means use of a third party (either an affiliated entity within '
        "a corporate group or an entity external to the corporate group) by an NBFC to "
        "perform activities on a continuing basis that would normally be undertaken by "
        "the NBFC itself.",
    ),
    (
        "RBI", "RBI-OUT-2025-S14", "financial",
        '[Para 14] "Material Outsourcing" - arrangements which, if disrupted, have '
        "potential to significantly impact business operations, reputation, "
        "profitability, or customer service. Materiality is assessed via: importance/risk "
        "significance of the activity; impact on earnings, solvency, liquidity, capital; "
        "reputational effect; cost as proportion of total operating costs; aggregate "
        "exposure to the service provider; significance for customer protection.",
    ),
    (
        "RBI", "RBI-OUT-2025-S15", "prohibited",
        "[Para 15] NBFCs shall NOT outsource core management functions: Internal Audit; "
        "Strategic and compliance functions; decision-making functions including KYC "
        "compliance determination, loan sanction approvals, and investment portfolio "
        "management. (Exception: group entities may handle these within the conglomerate "
        "under the conditions in Paras 45-51.)",
    ),
    (
        "RBI", "RBI-OUT-2025-S4.2", "general",
        "[Para 4(2)] Excluded from financial-services outsourcing (Chapter III): courier "
        "services, catering, housekeeping, janitorial services, premises security, "
        "records archival, and other unrelated support activities.",
    ),
    (
        "RBI", "RBI-OUT-2025-S5.2", "general",
        "[Para 5(2)] Excluded from IT outsourcing: corporate internet banking obtained as "
        "a customer, external audit/security review services, SMS gateways, IT hardware "
        "procurement, licensed software/CBS on subscription with vendor-provided upgrades, "
        "OEM maintenance services, financial-regulator applications (CCIL/NSE/BSE), "
        "SWIFT/Reuters/Bloomberg platforms, off-the-shelf products with minimal "
        "customisation, Centralised Payment System services, Business Correspondent and "
        "payroll processing services.",
    ),
    (
        "RBI", "RBI-IT-2023-S3a.iv", "it",
        "[RBI Outsourcing of IT Services Directions, 2023 - Section 3(a)(iv)] IT "
        "outsourcing includes: IT infrastructure management/maintenance/support; network "
        "and security solutions; application development, maintenance and testing "
        "(incl. Application Service Providers); data centre services; cloud computing "
        "services; managed security services; management of IT infrastructure for the "
        "payment system ecosystem.",
    ),
    (
        "RBI", "RBI-IT-2023-S3a.ii", "it",
        '[Section 3(a)(ii)] "Material Outsourcing of IT Services" - arrangements which, '
        "if disrupted or compromised, could significantly impact the RE's business "
        "operations, or materially impact customers via unauthorised access, loss, or "
        "theft of customer information.",
    ),
    (
        "RBI", "RBI-IT-2023-AppIII.A", "general",
        "[Appendix III(A)] Excluded from IT outsourcing: corporate internet banking "
        "obtained as a customer; acquisition of IT software/product/application (CBS, "
        "database, security solutions) on licence or subscription; OEM maintenance "
        "services (incl. security patches, bug fixes); applications provided by "
        "financial-sector regulators/institutions (CCIL, NSE, BSE); platforms by "
        "Reuters/Bloomberg/SWIFT; off-the-shelf products with no/minimal customisation.",
    ),
    (
        "RBI", "RBI-IT-2023-S9", "it",
        "[Section 9] An RE intending to outsource any IT activity shall put in place a "
        "comprehensive Board-approved IT outsourcing policy before engaging a service "
        "provider.",
    ),
    (
        "SEBI", "SEBI-MC-IA-S12.5", "prohibited",
        "[SEBI Master Circular for Investment Advisers, Section 12, Clause 12.5] "
        "Intermediaries shall NOT outsource their core business activities and "
        "compliance functions. For an Investment Adviser, this covers advisory "
        "decision-making and compliance oversight.",
    ),
    (
        "SEBI", "SEBI-MC-IA-S12.6", "financial",
        "[Clause 12.6] Where other activities ARE outsourced, the intermediary remains "
        "responsible for reporting suspicious transactions to FIU/competent authorities, "
        "and for compliance with SEBI KYC Registration Agency (KRA) Regulations, 2011 in "
        "respect of outsourced KYC activities.",
    ),
    (
        "SEBI", "SEBI-MC-IA-S5", "it",
        "[Section 5] Where Investment Advisers use SaaS/cloud-based solutions, critical "
        "client/financial data must remain within the legal boundary of India, not move "
        "cross-border via outsourced cloud services.",
    ),
]

clauses_table = sa.table(
    "regulator_clauses",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("version", sa.String),
    sa.column("effective_from", sa.DateTime(timezone=True)),
    sa.column("regulator", sa.String),
    sa.column("clause_ref", sa.String),
    sa.column("text", sa.Text),
    sa.column("tags", sa.String),
)


def upgrade() -> None:
    bind = op.get_bind()
    new_refs = [ref for _, ref, _, _ in CLAUSES]
    all_refs = OLD_PLACEHOLDER_REFS + new_refs
    # delete-then-insert by clause_ref makes this safe to re-run
    bind.execute(
        sa.text("DELETE FROM regulator_clauses WHERE clause_ref = ANY(:refs)"),
        {"refs": all_refs},
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        clauses_table,
        [
            {
                "id": uuid.uuid4(),
                "version": "v1",
                "effective_from": now,
                "regulator": regulator,
                "clause_ref": ref,
                "text": text,
                "tags": tags,
            }
            for regulator, ref, tags, text in CLAUSES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    new_refs = [ref for _, ref, _, _ in CLAUSES]
    bind.execute(
        sa.text("DELETE FROM regulator_clauses WHERE clause_ref = ANY(:refs)"),
        {"refs": new_refs},
    )
