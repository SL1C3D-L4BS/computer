/**
 * Surface 2: Pending Approvals
 *
 * Lists commitments in PENDING status that require family confirmation.
 * Approval calls runtime-kernel POST /commitments/{id}/approve.
 *
 * Data source: ComputerState.pending_commitments (status: PENDING)
 * Reference: docs/product/continuity-and-followup-model.md
 */
import Link from "next/link";
import { fetchPendingApprovals, type PendingApproval } from "@/lib/api";

export const dynamic = "force-dynamic";

function formatDeadline(iso: string | null): string {
  if (!iso) return "No deadline";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    const diffH = Math.round(diffMs / 3600000);
    if (diffH < 0) return `Overdue by ${-diffH}h`;
    if (diffH < 24) return `Due in ${diffH}h`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function priorityColor(p: number): string {
  if (p >= 0.8) return "#ef4444";
  if (p >= 0.5) return "#f59e0b";
  return "#22c55e";
}

async function ApprovalsList() {
  let approvals: PendingApproval[] = [];
  let error: string | null = null;

  try {
    approvals = await fetchPendingApprovals("");
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load approvals";
  }

  if (error) {
    return (
      <div style={{ padding: "1rem", background: "#fff3f3", border: "1px solid #fca5a5", borderRadius: "6px", color: "#dc2626", fontSize: "0.875rem" }}>
        Could not connect to runtime-kernel: {error}
      </div>
    );
  }

  if (approvals.length === 0) {
    return (
      <p style={{ color: "#94a3b8", fontStyle: "italic" }}>
        No pending approvals. Items requiring confirmation will appear here.
      </p>
    );
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {approvals.map((approval) => (
        <li
          key={approval.id}
          style={{
            padding: "1rem",
            border: `1px solid ${priorityColor(approval.priority_score)}44`,
            borderLeft: `4px solid ${priorityColor(approval.priority_score)}`,
            borderRadius: "6px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: "0 0 0.4rem 0", fontWeight: 600, fontSize: "0.9rem" }}>
                {approval.description}
              </p>
              <div style={{ display: "flex", gap: "1rem", fontSize: "0.8rem", color: "#666" }}>
                <span>
                  Priority:{" "}
                  <strong style={{ color: priorityColor(approval.priority_score) }}>
                    {Math.round(approval.priority_score * 100)}%
                  </strong>
                </span>
                <span>{formatDeadline(approval.due_at)}</span>
                {approval.workflow_id && (
                  <span style={{ color: "#94a3b8" }}>wf: {approval.workflow_id.slice(0, 12)}…</span>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
              <ApproveButton commitmentId={approval.id} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ApproveButton({ commitmentId }: { commitmentId: string }) {
  return (
    <form
      action={async () => {
        "use server";
        // Server action: POST to runtime-kernel
        const { approveCommitment } = await import("@/lib/api");
        await approveCommitment(commitmentId, "family_web_user");
      }}
    >
      <button
        type="submit"
        style={{
          padding: "6px 16px",
          background: "#22c55e",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "0.8rem",
          fontWeight: "bold",
          fontFamily: "monospace",
        }}
      >
        Approve
      </button>
    </form>
  );
}

export default function ApprovalsPage() {
  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <Link href="/" style={{ color: "#4a9eff", textDecoration: "none", fontSize: "0.875rem" }}>
        ← back
      </Link>
      <h1 style={{ fontSize: "1.25rem", fontWeight: "bold", margin: "1rem 0 0.25rem 0" }}>
        Pending Approvals
      </h1>
      <p style={{ color: "#666", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
        Commitments awaiting confirmation. Priority is urgency × importance × recency.
      </p>
      {/* @ts-expect-error async server component */}
      <ApprovalsList />
    </main>
  );
}
