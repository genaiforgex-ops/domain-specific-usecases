"""First-boot seed data: 5 sample users, JFPSL playbook clauses, regulatory
corpus stubs, LegalBot knowledge base, and a few regulatory updates so the
News page is non-empty.

Idempotent — only inserts rows when the relevant table is empty.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rbac import Role
from app.core.security import hash_password
from app.models.contract_template import ContractTemplate
from app.models.news import RegulatoryUpdate
from app.models.playbook import KnowledgeBaseEntry, PlaybookClause, RegulatorySource
from app.models.tracked_source import TrackedSource
from app.models.user import User


# Default bootstrap password for seeded real-email accounts. Override with
# SEED_DEFAULT_PASSWORD (via settings.seed_default_password). Users should change
# it after first login.
_DEFAULT_PASSWORD = settings.seed_default_password

# Real company accounts — only used as fallback when IAM sync is not configured.
_USERS = [
    ("vikas.maurya@jiofinance.in", "Vikas Maurya", Role.SUPER_ADMIN),
    ("harsh.tomar@jiofinance.in", "Harsh Tomar", Role.LEGAL_ADMIN),
    ("pranav.gupta@jfs.in", "Pranav Gupta", Role.LEGAL_ADMIN),
    ("harish.neela@jiofinance.in", "Harish Neela", Role.LEGAL_USER),
    ("aneesh.gupta@jiofinance.in", "Aneesh Gupta", Role.BUSINESS_USER),
]

# Default regulator sources for the Regulatory Intelligence tracker (UC-06).
_TRACKED_SOURCES = [
    ("Reserve Bank of India", "https://www.rbi.org.in/", "RBI", "Banking", "web"),
    ("SEBI — Legal", "https://www.sebi.gov.in/legal.html", "SEBI", "Securities", "web"),
    ("ASCI", "https://www.ascionline.in/", "ASCI", "Advertising", "web"),
    ("IRDAI", "https://irdai.gov.in/home", "IRDAI", "Insurance", "web"),
]

# Legacy demo accounts to deactivate on startup (superseded by real accounts).
_LEGACY_DEMO_EMAILS = [
    "super.admin@jfpsl.in",
    "legal.admin@jfpsl.in",
    "legal.user@jfpsl.in",
    "business.user@jfpsl.in",
    "readonly@jfpsl.in",
]

_PLAYBOOK = [
    {
        "clause_type": "Limitation of Liability",
        "contract_type": "MSA",
        "standard_position": (
            "Each party's aggregate liability under this Agreement shall not exceed the fees paid "
            "by JFPSL to the Vendor in the twelve (12) months immediately preceding the event giving "
            "rise to the claim. Neither party shall be liable for indirect, incidental, or "
            "consequential damages."
        ),
        "risk_keywords": [
            "unlimited liability",
            "liability",
            "no cap",
            "any and all damages",
            "consequential",
        ],
        "notes": "Hard-cap mandated by JFPSL Risk policy.",
    },
    {
        "clause_type": "Indemnity",
        "contract_type": "MSA",
        "standard_position": (
            "Vendor shall indemnify, defend, and hold harmless JFPSL against all third-party claims "
            "arising from (a) IP infringement by the deliverables, (b) Vendor's gross negligence or "
            "wilful misconduct, and (c) breach of data protection or confidentiality obligations."
        ),
        "risk_keywords": ["indemnify", "indemnif", "hold harmless"],
        "notes": "JFPSL must receive indemnity for IP + data breach + gross negligence.",
    },
    {
        "clause_type": "Confidentiality",
        "contract_type": "ANY",
        "standard_position": (
            "Each party shall protect the other's Confidential Information using the same degree "
            "of care it uses to protect its own confidential information (and in any event no less "
            "than reasonable care), for a period of five (5) years from disclosure."
        ),
        "risk_keywords": ["confidential", "non-disclosure", "proprietary"],
        "notes": "5-year tail. Perpetual confidentiality should be flagged.",
    },
    {
        "clause_type": "Termination",
        "contract_type": "MSA",
        "standard_position": (
            "JFPSL may terminate this Agreement for convenience on thirty (30) days' prior written "
            "notice without penalty. Either party may terminate for material breach on cure-period "
            "expiry of fifteen (15) days."
        ),
        "risk_keywords": ["termination", "terminate", "exit", "wind-down"],
        "notes": "Termination-for-convenience right is non-negotiable for JFPSL.",
    },
    {
        "clause_type": "Data Protection",
        "contract_type": "ANY",
        "standard_position": (
            "Vendor shall process Personal Data only as a Data Processor on JFPSL's documented "
            "instructions, in compliance with the DPDP Act 2023, and shall notify JFPSL of any "
            "Personal Data Breach within 24 hours."
        ),
        "risk_keywords": ["personal data", "dpdp", "data protection", "privacy", "breach"],
        "notes": "DPDP 24-hour breach-notification SLA.",
        "is_required": True,
        "regulatory_tags": ["DPDP", "MSA", "ANY"],
        "insert_anchor_hint": "confidential",
        "fallback_text": (
            "Vendor shall process Personal Data only as a Data Processor on JFPSL's documented "
            "instructions, in compliance with the DPDP Act 2023, and shall notify JFPSL of any "
            "Personal Data Breach within 24 hours."
        ),
    },
    {
        "clause_type": "Governing Law",
        "contract_type": "ANY",
        "standard_position": (
            "This Agreement shall be governed by and construed in accordance with the laws of "
            "India. Courts at Mumbai shall have exclusive jurisdiction."
        ),
        "risk_keywords": ["governing law", "jurisdiction", "arbitration"],
        "notes": "Indian law + Mumbai courts only.",
        "is_required": True,
        "insert_anchor_hint": "termination",
    },
    {
        "clause_type": "Payment Terms",
        "contract_type": "MSA",
        "standard_position": (
            "JFPSL shall pay undisputed invoices within forty-five (45) days of receipt. Disputed "
            "amounts may be withheld until resolution."
        ),
        "risk_keywords": ["payment", "invoice", "fees", "interest"],
        "notes": "Net-45 standard. Anything shorter triggers Finance review.",
    },
]

_REGULATORY = [
    {
        "regulator": "RBI",
        "reference": "RBI/2023-24/Digital Lending Guidelines",
        "title": "Guidelines on Digital Lending — September 2022 (consolidated)",
        "content": (
            "These guidelines apply to all lending business sourced through digital channels by "
            "Regulated Entities (REs) including NBFCs and their Lending Service Providers. Key "
            "Fact Statement (KFS) must be furnished to the borrower before contract execution. "
            "All loan disbursals and repayments shall flow only through the RE's bank account "
            "(no pass-through accounts). Cooling-off period must be offered."
        ),
        "tags": ["Lending", "KFS", "NBFC", "Digital Lending"],
    },
    {
        "regulator": "RBI",
        "reference": "RBI Master Direction — Outsourcing of IT Services",
        "title": "Master Direction on Outsourcing of Information Technology Services",
        "content": (
            "REs outsourcing material IT activities to third parties shall maintain effective "
            "oversight, including a Board-approved IT Outsourcing policy, due diligence on "
            "service providers, exit strategies, and data localisation as per extant norms."
        ),
        "tags": ["Outsourcing", "IT", "Vendor Management"],
    },
    {
        "regulator": "SEBI",
        "reference": "SEBI (Investment Advisers) Regulations, 2013",
        "title": "SEBI Investment Advisers Regulations",
        "content": (
            "An entity acting as an Investment Adviser shall be registered with SEBI. Distribution "
            "and advisory activities must be segregated. Suitability assessment is mandatory "
            "before recommending investment products to clients."
        ),
        "tags": ["Investments", "Advisory", "Distribution"],
    },
    {
        "regulator": "IRDAI",
        "reference": "IRDAI Web Aggregator Regulations, 2017",
        "title": "Insurance Web Aggregators Regulations",
        "content": (
            "Entities displaying insurance products on websites and apps shall obtain Web "
            "Aggregator registration from IRDAI. Comparisons must be product-agnostic and "
            "remuneration disclosures are mandatory."
        ),
        "tags": ["Insurance", "Web Aggregator"],
    },
    {
        "regulator": "DPDP",
        "reference": "Digital Personal Data Protection Act, 2023",
        "title": "DPDP Act 2023",
        "content": (
            "Personal data may be processed only on the basis of free, specific, informed and "
            "unambiguous consent (or specified legitimate uses). Data Fiduciaries must publish a "
            "privacy notice, enable consent withdrawal, appoint a DPO for Significant DFs, and "
            "report breaches to the Data Protection Board."
        ),
        "tags": ["Data Privacy", "Consent", "DPO"],
    },
    {
        "regulator": "PMLA",
        "reference": "PMLA / FIU-IND KYC Master Directions",
        "title": "PMLA — KYC Master Directions",
        "content": (
            "Reporting Entities shall undertake Customer Due Diligence (CDD), risk-categorise "
            "customers, monitor transactions, and file STRs/CTRs with FIU-IND. PEP screening and "
            "periodic KYC refresh are mandatory."
        ),
        "tags": ["AML/KYC", "PMLA", "FIU"],
    },
    {
        "regulator": "Companies Act",
        "reference": "Companies Act, 2013 — Section 134",
        "title": "Board Report & Directors' Responsibility Statement",
        "content": (
            "Every Board Report shall include a Directors' Responsibility Statement, declaration "
            "of compliance with applicable laws, and report on internal financial controls and "
            "risk management."
        ),
        "tags": ["Corporate", "Board"],
    },
    {
        "regulator": "FEMA",
        "reference": "FEMA Notification 5(R)",
        "title": "FEMA — Foreign Currency Accounts by Resident Indians",
        "content": (
            "Regulations governing opening and operation of foreign currency accounts by "
            "residents in India. Cross-border remittance limits under the Liberalised Remittance "
            "Scheme (LRS) apply."
        ),
        "tags": ["FEMA", "Forex"],
    },
]

_KB = [
    {
        "topic": "Can we share customer data with a co-lending partner?",
        "keywords": ["co-lending", "customer data", "share", "partner", "data sharing"],
        "answer": (
            "Customer data may be shared with a co-lending partner ONLY under a signed Data "
            "Sharing Agreement that (a) names the partner as Data Processor for the limited "
            "purpose of co-lending operations, (b) imposes DPDP-compliant safeguards, (c) "
            "restricts sub-processing, and (d) flows down a 24-hour breach-notification SLA. "
            "Any onward transfer requires fresh JFPSL Legal sign-off."
        ),
        "citations": [
            {"reference": "DPDP Act 2023", "regulator": "DPDP"},
            {"reference": "RBI Digital Lending Guidelines", "regulator": "RBI"},
        ],
    },
    {
        "topic": "Standard liability cap in vendor MSAs",
        "keywords": ["liability", "cap", "msa", "vendor", "limitation"],
        "answer": (
            "JFPSL's standard position is an aggregate liability cap equal to fees paid in the "
            "preceding 12 months, with the usual carve-outs (IP infringement, gross negligence/"
            "wilful misconduct, breach of confidentiality, indemnity obligations, data-breach "
            "liability). Unlimited liability for these carve-outs is required."
        ),
        "citations": [{"reference": "JFPSL Playbook — Limitation of Liability", "regulator": "Internal"}],
    },
    {
        "topic": "KFS requirement under RBI Digital Lending Guidelines",
        "keywords": ["kfs", "key fact statement", "digital lending", "rbi", "loan"],
        "answer": (
            "A Key Fact Statement (KFS) must be furnished to the borrower BEFORE contract "
            "execution for every digital loan. It must disclose the all-inclusive APR, the "
            "computation methodology, recovery mechanism, grievance redressal officer, and "
            "cooling-off period. KFS shall be in a standardised format and digitally signed."
        ),
        "citations": [{"reference": "RBI Digital Lending Guidelines", "regulator": "RBI"}],
    },
    {
        "topic": "FEMA applicability for cross-border vendor payments",
        "keywords": ["fema", "vendor payment", "cross-border", "foreign currency", "lrs"],
        "answer": (
            "Cross-border vendor payments must be routed through an Authorised Dealer (AD) bank "
            "with a duly classified purpose code. Software/services payments typically fall "
            "under code S0218 or similar. TDS u/s 195 + 15CA/CB compliance applies in parallel. "
            "Avoid routing through individual employee LRS limits."
        ),
        "citations": [{"reference": "FEMA Notification 5(R)", "regulator": "FEMA"}],
    },
    {
        "topic": "Marketing communication review — fair practices",
        "keywords": ["marketing", "communication", "fair practices", "advertising", "review"],
        "answer": (
            "All consumer-facing marketing must comply with the RBI Fair Practices Code: no "
            "misleading claims, no hidden fees, all material terms (APR, processing fees, "
            "tenure) prominently displayed, and standard disclaimers in regional languages "
            "where applicable. Legal sign-off required before publication."
        ),
        "citations": [{"reference": "RBI Fair Practices Code", "regulator": "RBI"}],
    },
]

_NEWS = [
    {
        "source": "RBI",
        "title": "RBI tightens norms for co-lending arrangements between banks and NBFCs",
        "full_text": (
            "The Reserve Bank of India has issued revised guidelines on co-lending arrangements "
            "between banks and NBFCs. The framework now mandates clearer customer disclosures, "
            "tighter operational controls, and an explicit grievance redressal mechanism. NBFCs "
            "must update their co-lending agreements within ninety days."
        ),
        "days_ago": 2,
        "url": "https://www.rbi.org.in/circulars/co-lending-2026",
    },
    {
        "source": "SEBI",
        "title": "SEBI extends timelines for mutual fund nomination compliance",
        "full_text": (
            "SEBI has extended the deadline for mandatory nomination updates for mutual fund "
            "folios. The new compliance date is end of next quarter. Asset Management Companies "
            "are advised to communicate the extension to distributors and unit holders."
        ),
        "days_ago": 5,
        "url": "https://www.sebi.gov.in/circulars/mf-nomination-2026",
    },
    {
        "source": "DPDP",
        "title": "Draft DPDP Rules released for stakeholder consultation",
        "full_text": (
            "The Ministry of Electronics and IT has released draft rules under the Digital "
            "Personal Data Protection Act, 2023, covering consent artifacts, Significant Data "
            "Fiduciary thresholds, and breach-notification timelines. Comments are invited from "
            "industry stakeholders within forty-five days. Implementation is expected within "
            "twelve months of finalisation."
        ),
        "days_ago": 1,
        "url": "https://www.meity.gov.in/dpdp-draft-rules",
    },
    {
        "source": "IRDAI",
        "title": "IRDAI permits insurers to use AI for claims processing under governance framework",
        "full_text": (
            "IRDAI has issued a circular permitting insurers to deploy AI/ML models for claims "
            "triage and processing, subject to a Board-approved AI governance framework, audit "
            "trails, and explainability standards. Quarterly model performance reports must be "
            "filed with IRDAI."
        ),
        "days_ago": 8,
        "url": "https://www.irdai.gov.in/circulars/ai-governance",
    },
]


def seed_all(db: Session) -> None:
    # Users are managed centrally via IAM when configured (sync runs at app startup).
    # Fall back to local seed list only when IAM sync is not configured.
    if not settings.iam_sync_enabled:
        for email, name, role in _USERS:
            existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing is None:
                db.add(
                    User(
                        email=email,
                        full_name=name,
                        hashed_password=hash_password(_DEFAULT_PASSWORD),
                        role=role.value,
                        is_active=True,
                    )
                )
    # Permanently remove superseded demo accounts (and detach/clean their refs).
    from app.services.user_service import hard_delete_user

    for legacy_email in _LEGACY_DEMO_EMAILS:
        legacy = db.execute(select(User).where(User.email == legacy_email)).scalar_one_or_none()
        if legacy is not None:
            hard_delete_user(db, legacy.id)
    # Flush so later seed steps (e.g. templates, tasks) can resolve user IDs.
    db.flush()

    # Default regulator sources (per-URL idempotent).
    for name, url, regulator, category, stype in _TRACKED_SOURCES:
        exists = db.execute(select(TrackedSource).where(TrackedSource.url == url)).scalar_one_or_none()
        if exists is None:
            db.add(
                TrackedSource(
                    name=name, url=url, regulator=regulator, category=category, source_type=stype
                )
            )
    db.flush()

    if db.execute(select(PlaybookClause).limit(1)).scalar_one_or_none() is None:
        for p in _PLAYBOOK:
            db.add(PlaybookClause(**p))
        db.flush()
        from app.models.clause_bank import ClauseBankEntry

        liability = db.execute(
            select(PlaybookClause).where(PlaybookClause.clause_type == "Limitation of Liability")
        ).scalar_one_or_none()
        data_prot = db.execute(
            select(PlaybookClause).where(PlaybookClause.clause_type == "Data Protection")
        ).scalar_one_or_none()
        if liability:
            db.add(
                ClauseBankEntry(
                    playbook_clause_id=liability.id,
                    contract_type="MSA",
                    clause_type="Limitation of Liability",
                    tier="preferred",
                    title="Mutual 12-month liability cap",
                    body_text=liability.standard_position,
                )
            )
        if data_prot:
            db.add(
                ClauseBankEntry(
                    playbook_clause_id=data_prot.id,
                    contract_type="ANY",
                    clause_type="Data Protection",
                    tier="preferred",
                    title="DPDP data protection clause",
                    body_text=data_prot.fallback_text or data_prot.standard_position,
                    regulatory_refs=["DPDP Act 2023"],
                )
            )

    if db.execute(select(ContractTemplate).limit(1)).scalar_one_or_none() is None:
        admin = db.execute(
            select(User)
            .where(User.role.in_([Role.SUPER_ADMIN.value, Role.LEGAL_ADMIN.value]))
            .order_by(User.id)
        ).scalars().first()
        db.add(
            ContractTemplate(
                contract_type="MSA",
                name="JFPSL Standard MSA 2025",
                description="Default master services agreement template for vendor onboarding.",
                template_text=(
                    "MASTER SERVICES AGREEMENT\n\n"
                    "This Agreement is entered into between Jio Finance Platform Ltd ('JFPSL') "
                    "and the Vendor named in the order form.\n\n"
                    "1. Services. Vendor shall provide the services described in each Statement of Work.\n\n"
                    "2. Limitation of Liability. Each party's aggregate liability shall not exceed fees "
                    "paid in the preceding twelve (12) months. Neither party is liable for indirect damages.\n\n"
                    "3. Indemnity. Vendor indemnifies JFPSL for IP infringement, gross negligence, "
                    "and data protection breaches.\n\n"
                    "4. Termination. JFPSL may terminate for convenience on thirty (30) days' notice.\n\n"
                    "5. Confidentiality. Five (5) year confidentiality term applies to all Confidential Information.\n"
                ),
                created_by_id=admin.id if admin else None,
            )
        )
        db.add(
            ContractTemplate(
                contract_type="NDA",
                name="JFPSL Mutual NDA 2025",
                description="Standard mutual non-disclosure agreement for vendor discussions.",
                template_text=(
                    "MUTUAL NON-DISCLOSURE AGREEMENT\n\n"
                    "Jio Finance Platform Ltd and the Vendor wish to exchange confidential information.\n\n"
                    "1. Confidential Information means all non-public business, technical, and financial data.\n\n"
                    "2. Each party shall protect the other's Confidential Information with reasonable care "
                    "for five (5) years from disclosure.\n\n"
                    "3. Standard exclusions apply for public domain, prior knowledge, and independent development.\n\n"
                    "4. Governing law: laws of India. Courts at Mumbai shall have exclusive jurisdiction.\n"
                ),
                created_by_id=admin.id if admin else None,
            )
        )

    if db.execute(select(RegulatorySource).limit(1)).scalar_one_or_none() is None:
        now = datetime.now(timezone.utc)
        for r in _REGULATORY:
            db.add(
                RegulatorySource(
                    regulator=r["regulator"],
                    reference=r["reference"],
                    title=r["title"],
                    content=r["content"],
                    tags=r["tags"],
                    published_on=now - timedelta(days=90),
                )
            )

    if db.execute(select(KnowledgeBaseEntry).limit(1)).scalar_one_or_none() is None:
        for k in _KB:
            db.add(KnowledgeBaseEntry(**k))

    if db.execute(select(RegulatoryUpdate).limit(1)).scalar_one_or_none() is None:
        from app.orchestrator import tasks as orch_tasks

        now = datetime.now(timezone.utc)
        for n in _NEWS:
            analysis = orch_tasks.analyse_regulatory_update(
                n["source"], n["title"], n["full_text"]
            )
            db.add(
                RegulatoryUpdate(
                    source=n["source"],
                    title=n["title"],
                    summary=analysis.summary,
                    full_text=n["full_text"],
                    url=n["url"],
                    tags=analysis.tags,
                    relevance_score=analysis.relevance_score,
                    status="for_information",
                    published_at=now - timedelta(days=n["days_ago"]),
                )
            )

    db.commit()
