"""Importing the models registers them with SQLAlchemy's metadata."""

from app.models.audit import AuditLog  # noqa: F401
from app.models.chat import ChatAttachment, ChatSession, ChatShare, ChatTurn  # noqa: F401
from app.models.llm_usage import LLMUsageLog  # noqa: F401
from app.models.comparison import DocumentComparison  # noqa: F401
from app.models.contract import Contract, ContractClause  # noqa: F401
from app.models.contract_revision import ContractRevision  # noqa: F401
from app.models.contract_template import ContractTemplate  # noqa: F401
from app.models.feature_request import FeatureRequest  # noqa: F401
from app.models.email_draft import EmailDraft  # noqa: F401
from app.models.gmail_credential import GmailCredential  # noqa: F401
from app.models.gmail_settings import GmailSettings  # noqa: F401
from app.models.msa import MSAEmail, MSATracker  # noqa: F401
from app.models.msa_share import MSAShare  # noqa: F401
from app.models.msa_prompt_revision import MSAPromptRevision  # noqa: F401
from app.models.msa_version import MSADocumentVersion  # noqa: F401
from app.models.negotiation_memory import NegotiationMemory  # noqa: F401
from app.models.notification import Notification, NotificationSetting  # noqa: F401
from app.models.clause_bank import ClauseBankEntry  # noqa: F401
from app.models.negotiation_task import NegotiationChangeTask  # noqa: F401
from app.models.news import RegulatoryUpdate  # noqa: F401
from app.models.regulatory_corpus import (  # noqa: F401
    RegulatoryChunk,
    RegulatoryDocument,
)
from app.models.tracked_source import TrackedSource  # noqa: F401
from app.models.playbook import KnowledgeBaseEntry, PlaybookClause, RegulatorySource  # noqa: F401
from app.models.query import LegalBotQuery  # noqa: F401
from app.models.research import ResearchNote  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.user import User  # noqa: F401
