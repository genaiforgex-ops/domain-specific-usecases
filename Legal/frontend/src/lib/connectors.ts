import type { Permission } from "@/types";

export type ConnectorId =
  | "gmail"
  | "google_drive"
  | "google_calendar"
  | "google_docs"
  | "slack"
  | "notion"
  | "microsoft_teams";

export type ConnectorCategory = "google_workspace" | "productivity" | "storage" | "all";

export interface ConnectorDefinition {
  id: ConnectorId;
  name: string;
  description: string;
  category: Exclude<ConnectorCategory, "all">;
  popularity?: string;
  /** When false, shown as coming soon — no configure action yet. */
  available: boolean;
  permissions?: Permission[];
}

export const CONNECTOR_CATEGORIES: { id: ConnectorCategory; label: string }[] = [
  { id: "all", label: "All connectors" },
  { id: "google_workspace", label: "Google Workspace" },
  { id: "productivity", label: "Productivity" },
  { id: "storage", label: "Storage" },
];

/** Central registry — add new connectors here as backends are implemented. */
export const CONNECTORS: ConnectorDefinition[] = [
  {
    id: "gmail",
    name: "Gmail",
    description: "Read labelled mail, extract tasks, draft AI replies, and send vendor threads.",
    category: "google_workspace",
    popularity: "Most used",
    available: true,
    permissions: ["task_management", "msa_automation"],
  },
  {
    id: "google_drive",
    name: "Google Drive",
    description: "Import contract files and attach redlines from Drive folders.",
    category: "google_workspace",
    popularity: "Popular",
    available: false,
    permissions: ["contract_review", "msa_automation"],
  },
  {
    id: "google_calendar",
    name: "Google Calendar",
    description: "Sync task due dates and hearing deadlines to your calendar.",
    category: "google_workspace",
    available: false,
    permissions: ["task_management"],
  },
  {
    id: "google_docs",
    name: "Google Docs",
    description: "Open and compare Docs-native contracts alongside DOCX workflows.",
    category: "google_workspace",
    available: false,
    permissions: ["contract_review"],
  },
  {
    id: "notion",
    name: "Notion",
    description: "Push research notes and playbook updates to a Notion workspace.",
    category: "productivity",
    available: false,
    permissions: ["legal_research"],
  },
  {
    id: "slack",
    name: "Slack",
    description: "Notify legal channels when tasks are overdue or MSAs need review.",
    category: "productivity",
    available: false,
    permissions: ["task_management"],
  },
  {
    id: "microsoft_teams",
    name: "Microsoft Teams",
    description: "Escalate LegalBot Tier-2 queries to a Teams channel.",
    category: "productivity",
    available: false,
    permissions: ["legal_bot_use"],
  },
];

export function connectorById(id: string): ConnectorDefinition | undefined {
  return CONNECTORS.find((c) => c.id === id);
}
