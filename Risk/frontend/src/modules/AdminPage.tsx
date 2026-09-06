import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader, Card, DataTable, Button, Badge } from "../components/ui";

export function AdminPage() {
  const [configs, setConfigs] = useState<Array<{ module: string; kill_switch: boolean; confidence_threshold: number | null }>>([]);

  useEffect(() => {
    api.get<typeof configs>("/admin/ai-config").then(setConfigs);
  }, []);

  const toggle = async (module: string, kill: boolean) => {
    await api.patch(`/admin/ai-config/${module}`, { kill_switch: kill });
    const updated = await api.get<typeof configs>("/admin/ai-config");
    setConfigs(updated);
  };

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="Administration"
        subtitle="AI kill-switches, confidence thresholds, and platform configuration."
      />

      <Card>
        <h2 className="card__title">Module AI configuration</h2>
        <p style={{ margin: "0 0 20px", color: "var(--slate-500)", fontSize: 14 }}>
          Disabling AI leaves manual workflows fully available. All settings are audit-logged.
        </p>
        <DataTable>
          <thead>
            <tr>
              <th>Module</th>
              <th>Status</th>
              <th>Confidence threshold</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {configs.map((c) => (
              <tr key={c.module}>
                <td><strong>{c.module}</strong></td>
                <td>
                  {c.kill_switch ? (
                    <Badge variant="danger">AI disabled</Badge>
                  ) : (
                    <Badge variant="success">AI enabled</Badge>
                  )}
                </td>
                <td>{c.confidence_threshold != null ? `${Math.round(c.confidence_threshold * 100)}%` : "Default"}</td>
                <td>
                  <Button
                    size="sm"
                    variant={c.kill_switch ? "primary" : "danger"}
                    onClick={() => toggle(c.module, !c.kill_switch)}
                  >
                    {c.kill_switch ? "Enable AI" : "Kill switch"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </Card>
    </div>
  );
}
