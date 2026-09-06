import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { formatDate } from "@/lib/utils";
import type { AuditLogEntry } from "@/types";

const MODULES = [
  "",
  "auth",
  "users",
  "contract_review",
  "document_comparison",
  "legal_bot",
  "legal_research",
  "msa_automation",
  "legal_news",
  "playbook",
];

export function AuditLogPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const seesAll = hasPermission(user, "audit_log_all");

  const load = useCallback(async () => {
    setRows(
      await api.listAudit({
        module: module || undefined,
        action_type: action || undefined,
        limit: 500,
      }),
    );
  }, [module, action]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="Audit Log"
        subtitle={
          <>
            Immutable record of every AI action and human decision. Retention target: 7 years (RBI).{" "}
            {seesAll ? "Viewing all entries." : "Viewing your own entries only."}
          </>
        }
      />
      <Card>
        <div className="flex gap-3 flex-wrap">
          <Select value={module} onChange={(e) => setModule(e.target.value)}>
            {MODULES.map((m) => (
              <option key={m} value={m}>
                {m || "All modules"}
              </option>
            ))}
          </Select>
          <Input
            placeholder="action_type filter"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </div>
      </Card>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-label-secondary border-b border-separator/30">
              <tr>
                <th className="py-2 pr-2">When</th>
                <th className="py-2 pr-2">User</th>
                <th className="py-2 pr-2">Role</th>
                <th className="py-2 pr-2">Module</th>
                <th className="py-2 pr-2">Action</th>
                <th className="py-2 pr-2">Decision</th>
                <th className="py-2 pr-2">Conf.</th>
                <th className="py-2 pr-2">Model</th>
                <th className="py-2 pr-2">Input</th>
                <th className="py-2">AI Output</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-separator/20 align-top">
                  <td className="py-2 pr-2 whitespace-nowrap text-label-secondary">{formatDate(r.timestamp)}</td>
                  <td className="py-2 pr-2">#{r.user_id ?? "—"}</td>
                  <td className="py-2 pr-2">{r.role}</td>
                  <td className="py-2 pr-2">{r.module}</td>
                  <td className="py-2 pr-2 font-mono">{r.action_type}</td>
                  <td className="py-2 pr-2">
                    {r.human_decision ? (
                      <Badge className="bg-bg-secondary text-label-secondary border-separator/40">
                        {r.human_decision}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 pr-2">
                    {r.confidence_score != null ? Math.round(r.confidence_score * 100) + "%" : "—"}
                  </td>
                  <td className="py-2 pr-2 font-mono text-[10px]">{r.model_version || "—"}</td>
                  <td className="py-2 pr-2 max-w-xs truncate">{r.input_summary || "—"}</td>
                  <td className="py-2 max-w-xs truncate">{r.ai_output_summary || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="text-sm text-label-secondary py-4">No entries.</div>}
        </div>
      </Card>
    </div>
  );
}
