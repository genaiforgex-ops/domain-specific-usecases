"""Role-based access control matrix.

Single source of truth for which roles can use which permissions.
Mirrored on the frontend by `lib/auth.ts` — keep them in sync.
"""

from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    LEGAL_ADMIN = "legal_admin"
    LEGAL_USER = "legal_user"
    BUSINESS_USER = "business_user"
    READ_ONLY = "read_only"


class Permission(str, Enum):
    # Module access
    CONTRACT_REVIEW = "contract_review"
    DOCUMENT_COMPARISON = "document_comparison"
    LEGAL_BOT_USE = "legal_bot_use"
    LEGAL_RESEARCH = "legal_research"
    MSA_AUTOMATION = "msa_automation"
    MSA_SHARED_VIEW = "msa_shared_view"
    LEGAL_NEWS_FULL = "legal_news_full"
    LEGAL_NEWS_DIGEST = "legal_news_digest"

    # Admin / governance
    USER_MANAGEMENT = "user_management"
    PLAYBOOK_MANAGEMENT = "playbook_management"
    AUDIT_LOG_ALL = "audit_log_all"
    AUDIT_LOG_OWN = "audit_log_own"

    # AI decisions
    APPROVE_AI_OUTPUT = "approve_ai_output"
    SEND_EMAIL = "send_email"

    # Task manager
    TASK_MANAGEMENT = "task_management"

    # Build Studio
    BUILD_REQUESTS = "build_requests"
    BUILD_PR_APPROVE = "build_pr_approve"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: {p for p in Permission},
    Role.LEGAL_ADMIN: {
        Permission.CONTRACT_REVIEW,
        Permission.DOCUMENT_COMPARISON,
        Permission.LEGAL_BOT_USE,
        Permission.LEGAL_RESEARCH,
        Permission.MSA_AUTOMATION,
        Permission.LEGAL_NEWS_FULL,
        Permission.LEGAL_NEWS_DIGEST,
        Permission.PLAYBOOK_MANAGEMENT,
        Permission.AUDIT_LOG_ALL,
        Permission.AUDIT_LOG_OWN,
        Permission.APPROVE_AI_OUTPUT,
        Permission.SEND_EMAIL,
        Permission.TASK_MANAGEMENT,
        Permission.BUILD_REQUESTS,
        Permission.BUILD_PR_APPROVE,
    },
    Role.LEGAL_USER: {
        Permission.CONTRACT_REVIEW,
        Permission.DOCUMENT_COMPARISON,
        Permission.LEGAL_BOT_USE,
        Permission.LEGAL_RESEARCH,
        Permission.MSA_AUTOMATION,
        Permission.LEGAL_NEWS_FULL,
        Permission.LEGAL_NEWS_DIGEST,
        Permission.AUDIT_LOG_OWN,
        Permission.APPROVE_AI_OUTPUT,
        Permission.TASK_MANAGEMENT,
        Permission.BUILD_REQUESTS,
    },
    Role.BUSINESS_USER: {
        Permission.LEGAL_BOT_USE,
        Permission.AUDIT_LOG_OWN,
        Permission.TASK_MANAGEMENT,
        Permission.BUILD_REQUESTS,
        Permission.MSA_SHARED_VIEW,
    },
    Role.READ_ONLY: {
        Permission.LEGAL_NEWS_DIGEST,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
