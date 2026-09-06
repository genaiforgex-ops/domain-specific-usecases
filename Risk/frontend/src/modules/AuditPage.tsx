import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader, Card, DataTable, Badge, EmptyState, FormField, Input } from "../components/ui";

interface AuditEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor_email: string | null;
  created_at: string;
  payload_json: Record<string, unknown> | null;
}

export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const filtering = module.trim() !== "" || action.trim() !== "";

  useEffect(() => {
    // Debounced: this ran on every keystroke, so typing "ai.invocation" fired
    // thirteen queries and the UI rendered the results of whichever landed last.
    setLoading(true);
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ limit: "200" });
      if (module.trim()) params.set("entity_type", module.trim());
      if (action.trim()) params.set("event_type", action.trim());
      api
        .get<AuditEvent[]>(`/audit?${params.toString()}`)
        .then(setEvents)
        .catch(() => setEvents([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [module, action]);

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="Audit Log Explorer"
        subtitle="Immutable record of AI invocations, human decisions, logins, and configuration changes."
      />

      <Card>
        <div className="form-grid form-grid--2" style={{ marginBottom: "var(--space-5)" }}>
          <FormField label="Module (entity type)" hint="Matches any part of the name.">
            <Input
              placeholder="e.g. auth, user, dd_report, M1"
              value={module}
              onChange={(e) => setModule(e.target.value)}
            />
          </FormField>
          <FormField label="Action (event type)" hint="Matches any part of the name.">
            <Input
              placeholder="e.g. login, user.created, ai.invocation"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          </FormField>
        </div>

        {filtering && !loading && events.length > 0 && (
          <p style={{ margin: "0 0 var(--space-4)", fontSize: "var(--text-footnote)", color: "var(--color-label-secondary)" }}>
            {events.length === 200 ? "Showing the 200 most recent matches" : `${events.length} matching event${events.length === 1 ? "" : "s"}`}
          </p>
        )}

        {events.length === 0 ? (
          // A filtered miss is a different problem from an empty log — the old
          // copy told someone whose search returned nothing that the system had
          // recorded no activity at all.
          filtering ? (
            <EmptyState
              title="No matching events"
              description="No audit events match this Module and Action. Try a shorter search, or clear the boxes to see everything."
            />
          ) : (
            <EmptyState title="No audit events" description="Activity will appear as you use GenAIForge Risk modules." />
          )
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>When</th>
                <th>User</th>
                <th>Module</th>
                <th>Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleString()}</td>
                  <td>{e.actor_email ?? <span style={{ color: "var(--slate-500)" }}>—</span>}</td>
                  <td><span className="mono">{e.entity_type}</span></td>
                  <td>
                    <Badge variant={e.event_type.startsWith("ai.") ? "ai" : e.event_type === "login_failed" ? "danger" : "neutral"}>
                      {e.event_type}
                    </Badge>
                  </td>
                  <td>
                    <code style={{ fontSize: 11, color: "var(--slate-600)" }}>
                      {e.payload_json ? JSON.stringify(e.payload_json).slice(0, 60) + "…" : "—"}
                    </code>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
    </div>
  );
}
