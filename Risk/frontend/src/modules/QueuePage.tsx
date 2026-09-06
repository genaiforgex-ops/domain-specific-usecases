import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ClassificationJob } from "../api/client";
import { PageHeader, Card, DataTable, StatusBadge, Button, Badge, EmptyState } from "../components/ui";
import { formatLabel, formatPercent } from "../utils/format";

export function QueuePage() {
  const [jobs, setJobs] = useState<ClassificationJob[]>([]);

  useEffect(() => {
    api.get<ClassificationJob[]>("/classifications").then(setJobs).catch(() => {});
  }, []);

  const pending = jobs.filter((j) => j.status === "ready");
  const processing = jobs.filter((j) => j.status === "pending" || j.status === "processing");

  return (
    <div>
      <PageHeader
        breadcrumb="Workspace"
        title="My Queue"
        subtitle="Items awaiting your review across risk modules."
        action={pending.length > 0 ? <Badge variant="warning">{pending.length} pending</Badge> : undefined}
      />

      {processing.length > 0 && (
        <Card className="mb-24">
          <h2 className="card__title">In progress</h2>
          <DataTable>
            <thead><tr><th>Module</th><th>Status</th><th>ID</th></tr></thead>
            <tbody>
              {processing.map((j) => (
                <tr key={j.id}>
                  <td>M1 Classification</td>
                  <td><StatusBadge status={j.status} /></td>
                  <td className="mono">{j.id.slice(0, 8)}…</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}

      <Card>
        <h2 className="card__title">Awaiting review</h2>
        {pending.length === 0 ? (
          <EmptyState title="Queue is clear" description="No classifications waiting for sign-off." />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Classification</th>
                <th>AI label</th>
                <th>Confidence</th>
                <th>Secondary review</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pending.map((j) => (
                <tr key={j.id}>
                  <td className="mono">{j.id.slice(0, 8)}…</td>
                  <td>{formatLabel(j.ai_label)}</td>
                  <td>{formatPercent(j.ai_confidence)}</td>
                  <td>{j.requires_secondary_review ? <Badge variant="warning">Yes</Badge> : "—"}</td>
                  <td>
                    <Link to={`/m1?job=${j.id}`}>
                      <Button size="sm" variant="primary">Review →</Button>
                    </Link>
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
