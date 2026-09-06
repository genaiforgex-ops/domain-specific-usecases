"""Add verified RBI/SEBI outsourcing clauses (v2) sourced from gazetted PDFs

Revision ID: 004
Revises: 003
Create Date: 2026-06-23

Sourced directly from the gazetted/master-circular PDFs supplied by the risk
team (not secondary republications):
  - RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025
    [RBI/DOR/2025-26/363, dated November 28, 2025]
  - SEBI Master Circular for Investment Advisers
    [SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/94, dated June 27, 2025],
    Section 13 "Guidelines on Outsourcing of Activities by Intermediaries"
    and Annexure H "Principles for Outsourcing for Intermediaries"

This lands as a NEW clause_library_version ("v2") rather than overwriting
"v1" (seeded by migration 003 from unverified secondary sources). Any
classification_jobs already pinned to clause_library_version="v1" keep
reading the old text; get_active_clause_version() picks "v2" going forward
since it has a later effective_from.

Scope note: the RBI (Payments Banks - Managing Risks in Outsourcing)
Directions, 2025 [RBI/DOR/2025-26/220] were also supplied but deliberately
excluded here. The `regulator` column only takes "RBI"/"SEBI" (exact match,
no entity sub-type), so NBFC- and Payments-Bank-specific provisions would
collapse into one undifferentiated RBI bucket - e.g. the Payments-Bank-only
duty to notify IBA's caution list on termination would appear to apply to
NBFCs too. Revisit if/when the schema can distinguish entity type.

Migration 003's "v1" rows are intentionally left untouched - cleanup of that
seed is a separate follow-up decision.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

CLAUSE_VERSION = "v2"

CLAUSES = [
    (
        "RBI", "RBI-NBFC-2025-P6.1", "general",
        '[NBFC Outsourcing Directions, 2025 - Para 6(1)] "Outsourcing" means use of '
        "a third party (either an affiliated entity within a corporate group or an "
        "entity external to the corporate group) by an NBFC to perform activities "
        "on a continuing basis that would normally be undertaken by the NBFC "
        'itself, now or in the future. "Continuing basis" includes agreements for '
        "a limited period.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P14", "financial",
        '[Para 14] "Material Outsourcing" means arrangements which, if disrupted, '
        "have the potential to significantly impact business operations, "
        "reputation, profitability, or customer service. Materiality is assessed "
        "on: (i) importance of the activity and significance of the risk it "
        "poses; (ii) potential impact on earnings, solvency, liquidity, funding, "
        "capital, and risk profile; (iii) likely reputational impact and effect on "
        "business objectives should the service provider fail to perform; (iv) "
        "cost as a proportion of total operating costs; (v) aggregate exposure to "
        "that service provider; (vi) significance for customer service and "
        "protection.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P15", "prohibited",
        "[Para 15] An NBFC shall not outsource core management functions "
        "including Internal Audit, strategic and compliance functions, and "
        "decision-making functions such as determining KYC compliance for "
        "opening deposit accounts, sanctioning loans (including retail loans), "
        "and management of investment portfolio. Proviso: for an NBFC in a "
        "group/conglomerate, these functions may be outsourced within the group "
        "subject to Paras 45-51. (Internal audit remains a management process "
        "even where individual internal auditors are engaged on contract.)",
    ),
    (
        "RBI", "RBI-NBFC-2025-P4.2", "general",
        "[Para 4(2)] Outsourcing-of-financial-services provisions (Chapter III) "
        "do not apply to: (i) IT services as defined in Para 58(1), unless "
        "specified otherwise in Chapter IV; (ii) activities unrelated to "
        "financial services such as courier use, staff catering, housekeeping "
        "and janitorial services, premises security, and movement/archiving of "
        "records.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P58", "it",
        '[Para 58(1)-(2)] "IT services" means IT services / IT-enabled services / '
        'IT activities. "Material Outsourcing of IT Services" means arrangements '
        "which, if disrupted or compromised, would significantly impact the "
        "NBFC's business operations, or have material impact on customers in the "
        "event of unauthorised access, loss, or theft of customer information.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P5.1", "it",
        "[Para 5(1)] Outsourcing of IT Services (Chapter IV) covers: IT "
        "infrastructure management, maintenance and support; network and "
        "security solutions and maintenance; application development, "
        "maintenance and testing by Application Service Providers (incl. ATM "
        "Switch ASPs); services and operations related to data centres; cloud "
        "computing services; managed security services; and management of IT "
        "infrastructure/technology services associated with the payment system "
        "ecosystem.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P5.2", "general",
        "[Para 5(2)] Excluded from IT-outsourcing provisions: corporate internet "
        "banking obtained as a corporate customer/sub-member of another "
        "Regulated Entity; external audit services (VA/PT, Information Systems "
        "Audit, security review); SMS gateways; procurement of IT hardware or "
        "appliances; licensed/subscribed IT software or product (e.g. Core "
        "Banking Solution, database, security solutions) including OEM upgrades "
        "or NBFC-requested change requests; OEM maintenance (incl. security "
        "patches and bug fixes); applications provided by financial-sector "
        "regulators/institutions (CCIL, NSE, BSE); platforms provided by "
        "Reuters/Bloomberg/SWIFT; off-the-shelf products with no or minimal "
        "customisation; services obtained as a sub-member of a Centralised "
        "Payment System; and Business Correspondent services, payroll "
        "processing, and statement printing.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P59", "prohibited",
        "[Para 59] For IT outsourcing, the service provider - if not a group "
        "company - shall not be owned or controlled by any director, key "
        "managerial personnel, or approver of the outsourcing arrangement of the "
        "NBFC, or their relatives. An exception may be made only with approval "
        "of the Board or a Committee of the Board, followed by appropriate "
        "disclosure, oversight and monitoring of the arrangement.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P61", "it",
        "[Para 61] An NBFC shall ensure cyber incidents are reported to it by the "
        "service provider without undue delay, so that the NBFC can in turn "
        "report the incident to RBI within six hours of detection by the "
        "service provider.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P62", "it",
        "[Para 62] An NBFC intending to outsource IT services shall put in place "
        "a comprehensive Board-approved IT outsourcing policy covering: roles "
        "and responsibilities of the Board, Senior Management, IT function and "
        "business function; criteria for selecting services/service providers; "
        "parameters defining material outsourcing; delegation of authority by "
        "risk and materiality; disaster recovery and business continuity plans; "
        "systems to monitor and review operations; and termination processes/"
        "exit strategies including continuity if a service provider exits.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P95", "it",
        "[Para 95] Outsourcing of Security Operations Centre (SOC) operations "
        "requires, in addition to the general IT-outsourcing controls: "
        "unambiguous identification of the owner of assets used to provide the "
        "service; the NBFC retaining oversight and ownership of rule definition, "
        "customisation, and related data/logs, metadata and analytics specific "
        "to the NBFC; periodic assessment of SOC functioning and physical "
        "facilities; integration of outsourced SOC reporting/escalation with the "
        "NBFC's incident-response process; and review of alert/event handling.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P97", "it",
        "[Paras 96-97] An NBFC using cloud computing services (IaaS/PaaS/SaaS and "
        "other CSP offerings) must, beyond general IT-outsourcing requirements: "
        "assess business strategy and cost impact of cloud adoption; ensure the "
        "Board-approved IT outsourcing policy addresses the full data lifecycle "
        "(generation through permanent erasure); account for multi-tenancy and "
        "multi-location data-storage risk; implement cloud security best "
        "practices consistent with the NBFC-CSP shared-responsibility model; and "
        "adopt a documented cloud-adoption/governance policy covering regulatory "
        "compliance (privacy, security, data sovereignty, recoverability, data "
        "storage) and ongoing CSP due diligence.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P16to19", "financial",
        "[Paras 16-19] Outsourcing of financial services does not require prior "
        "RBI approval but remains subject to RBI on-site/off-site monitoring and "
        "inspection. Outsourcing does not diminish the NBFC's obligations to "
        "customers or RBI; the NBFC remains responsible for the actions of its "
        "service provider (including DSAs/DMAs and recovery agents) and for the "
        "confidentiality of customer information held by the provider, and "
        "retains ultimate control of the outsourced activity. The NBFC remains "
        "responsible for filing CTRs/STRs to FIU for customer-related activities "
        "carried out by service providers.",
    ),
    (
        "RBI", "RBI-NBFC-2025-P23to28", "general",
        "[Paras 23-28] The NBFC must ensure confidentiality and security of "
        'customer information held by the service provider; provider access to '
        'it must be on a "need to know" basis; the NBFC must regularly review/'
        "monitor the provider's security practices and require disclosure of "
        "security breaches; safeguards must prevent co-mingling of data where a "
        "provider serves multiple entities; and the NBFC must immediately notify "
        "RBI of any breach of security or leakage of confidential customer "
        "information, remaining liable to customers for resulting damage.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-S13.3", "general",
        "[SEBI Master Circular for Investment Advisers, Section 13.3] "
        "Outsourcing is the use of one or more third parties - either within or "
        "outside the group - by a registered intermediary to perform the "
        "activities associated with the services it offers.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-S13.4", "financial",
        "[Section 13.4 / Annexure H] Outsourcing risks include operational, "
        "reputational, legal, country, strategic, exit-strategy, counterparty, "
        "concentration, and systemic risk. The Board/partners must maintain a "
        "comprehensive outsourcing policy and bear overall responsibility for "
        "it; an activity shall not be outsourced if doing so would impair the "
        "regulator's right to assess or its ability to supervise the "
        "intermediary's business.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-S13.5", "prohibited",
        "[Section 13.5] Intermediaries shall not outsource their core business "
        "activities and compliance functions (for example, for a stock broker: "
        "execution of orders and monitoring of clients' trading activity). KYC "
        "requirements must independently comply with SEBI {KYC (Know Your "
        "Client) Registration Agency} Regulations, 2011 and guidelines issued "
        "thereunder.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-S13.6", "financial",
        "[Section 13.6] Intermediaries remain responsible for reporting "
        "suspicious transactions to the Financial Intelligence Unit (FIU) or any "
        "other competent authority in respect of activities carried out by "
        "outsourced third parties.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-AnxH.3", "general",
        "[Annexure H, Principle 3] Outsourcing arrangements must not diminish "
        "the intermediary's ability to fulfil obligations to customers and "
        "regulators, nor impede effective regulatory supervision. The "
        "intermediary remains fully liable to investors for losses caused by the "
        "third party's failure and is responsible for grievance redressal "
        "arising from outsourced activities; facilities, premises, and data used "
        "to perform the outsourced activity are deemed those of the "
        "intermediary, and the regulator may access them at any time.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-AnxH.5", "general",
        "[Annexure H, Principle 5] Outsourcing must be governed by a written "
        "contract defining the activities outsourced, service/performance "
        "levels, mutual rights and liabilities, continuous-monitoring rights, "
        "sub-contracting conditions, confidentiality clauses surviving contract "
        "expiry, IT-security/business-continuity/disaster-recovery "
        "responsibilities, dispute-resolution mechanisms, termination/exit "
        "provisions, and the regulator's right to inspect records held by the "
        "third party.",
    ),
    (
        "SEBI", "SEBI-MC-IA-2025-AnxH.7", "general",
        "[Annexure H, Principle 7] The intermediary must require third parties "
        "to protect confidential intermediary and client information from "
        "intentional or inadvertent disclosure, limit third-party staff access "
        'to a "need to know" basis, and build safeguards against co-mingling of '
        "data where a single third party serves multiple entities.",
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
    # delete-then-insert by clause_ref makes this safe to re-run
    bind.execute(
        sa.text("DELETE FROM regulator_clauses WHERE clause_ref = ANY(:refs)"),
        {"refs": new_refs},
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        clauses_table,
        [
            {
                "id": uuid.uuid4(),
                "version": CLAUSE_VERSION,
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
