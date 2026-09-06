import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, FormAssignment } from "../../api/client";
import { downloadBlob } from "../../api/download";
import { useToast } from "../../app/ToastContext";
import { PageHeader, Card, DataTable, Button, StatusBadge, EmptyState } from "../../components/ui";

export function MyFormsPage() {
  const toast = useToast();
  const [assignments, setAssignments] = useState<FormAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    api.get<FormAssignment[]>("/forms/assignments/mine")
      .then(setAssignments)
      .finally(() => setLoading(false));
  }, []);

  const download = async (a: FormAssignment) => {
    setDownloadingId(a.id);
    try {
      await downloadBlob(`/forms/assignments/${a.id}/export.xlsx`, `${a.title}.xlsx`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  };

  if (loading) return <div className="empty-state">Loading your forms…</div>;

  return (
    <div>
      <PageHeader
        breadcrumb="Workspace"
        title="My Forms"
        subtitle="Vendor due diligence forms assigned to you."
      />
      {assignments.length === 0 ? (
        <EmptyState title="No forms assigned" description="When an admin assigns you a form, it will appear here." />
      ) : (
        <Card>
          <DataTable>
            <thead>
              <tr>
                <th>Title</th>
                <th>Vendor</th>
                <th>Status</th>
                <th>Classification</th>
                <th>Due</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.title}</strong></td>
                  <td>{a.vendor_legal_name ?? "—"}</td>
                  <td><StatusBadge status={a.status} /></td>
                  <td>
                    {a.classification_status ? (
                      <>
                        <StatusBadge status={a.classification_status} />
                        {a.classification_label && <> {a.classification_label.replace(/_/g, " ")}</>}
                      </>
                    ) : "—"}
                  </td>
                  <td>{a.due_at ? new Date(a.due_at).toLocaleDateString() : "—"}</td>
                  <td className="form-row-actions">
                    <Link to={`/my-forms/${a.id}`}>
                      <Button size="sm">{a.status === "submitted" ? "View" : "Open"}</Button>
                    </Link>
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={downloadingId === a.id}
                      onClick={() => download(a)}
                    >
                      Download
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}
    </div>
  );
}
