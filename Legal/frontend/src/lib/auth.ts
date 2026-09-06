import type { Permission, Role, User } from "@/types";

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  super_admin: [
    "contract_review",
    "document_comparison",
    "legal_bot_use",
    "legal_research",
    "msa_automation",
    "legal_news_full",
    "legal_news_digest",
    "user_management",
    "playbook_management",
    "audit_log_all",
    "audit_log_own",
    "approve_ai_output",
    "send_email",
    "task_management",
    "build_requests",
    "build_pr_approve",
  ],
  legal_admin: [
    "contract_review",
    "document_comparison",
    "legal_bot_use",
    "legal_research",
    "msa_automation",
    "legal_news_full",
    "legal_news_digest",
    "playbook_management",
    "audit_log_all",
    "audit_log_own",
    "approve_ai_output",
    "send_email",
    "task_management",
    "build_requests",
    "build_pr_approve",
  ],
  legal_user: [
    "contract_review",
    "document_comparison",
    "legal_bot_use",
    "legal_research",
    "msa_automation",
    "legal_news_full",
    "legal_news_digest",
    "audit_log_own",
    "approve_ai_output",
    "task_management",
    "build_requests",
  ],
  business_user: ["legal_bot_use", "audit_log_own", "task_management", "build_requests", "msa_shared_view"],
  read_only: ["legal_news_digest"],
};

export function hasPermission(user: User | null, ...perms: Permission[]): boolean {
  if (!user) return false;
  const granted = new Set(user.permissions?.length ? user.permissions : ROLE_PERMISSIONS[user.role]);
  return perms.some((p) => granted.has(p));
}

export function roleLabel(role: Role): string {
  switch (role) {
    case "super_admin":
      return "Super Admin";
    case "legal_admin":
      return "Legal Admin";
    case "legal_user":
      return "Legal User";
    case "business_user":
      return "Business User";
    case "read_only":
      return "Read Only";
  }
}
