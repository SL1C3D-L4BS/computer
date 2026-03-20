/**
 * Surface 1: Reminder / History Feed
 *
 * Shows past assistant actions: closed loops, abandoned loops, fulfilled commitments.
 * This is the accountability surface — proves Computer did what it said it would do.
 *
 * Data source: ComputerState.open_loops (status: CLOSED | ABANDONED | CANCELLED)
 * Reference: docs/product/continuity-and-followup-model.md
 */
import Link from "next/link";
import { fetchReminderHistory, type ReminderHistoryItem } from "@/lib/api";

export const dynamic = "force-dynamic";

function statusColor(status: string): string {
  return { CLOSED: "#22c55e", ABANDONED: "#f59e0b", CANCELLED: "#94a3b8" }[status] ?? "#94a3b8";
}

function statusLabel(status: string): string {
  return { CLOSED: "Resolved", ABANDONED: "Abandoned", CANCELLED: "Cancelled" }[status] ?? status;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric",
    });
  } catch {
    return iso;
  }
}

function FreshnessBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value > 0.5 ? "#22c55e" : value > 0.2 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <div
        style={{
          height: "6px",
          width: "60px",
          background: "#f0f0f0",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: "3px" }} />
      </div>
      <span style={{ fontSize: "0.75rem", color: "#666" }}>{pct}%</span>
    </div>
  );
}

async function ReminderFeed({ userId }: { userId: string }) {
  let items: ReminderHistoryItem[] = [];
  let error: string | null = null;

  try {
    items = await fetchReminderHistory(userId);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load history";
  }

  if (error) {
    return (
      <div style={{ padding: "1rem", background: "#fff3f3", border: "1px solid #fca5a5", borderRadius: "6px", color: "#dc2626", fontSize: "0.875rem" }}>
        Could not connect to runtime-kernel: {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <p style={{ color: "#94a3b8", fontStyle: "italic" }}>
        No history yet. Completed and abandoned loops will appear here.
      </p>
    );
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {items.map((item) => (
        <li
          key={item.id}
          style={{
            padding: "1rem",
            border: "1px solid #e0e0e0",
            borderRadius: "6px",
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: "0.5rem",
          }}
        >
          <div>
            <p style={{ margin: "0 0 0.25rem 0", fontWeight: 600, fontSize: "0.9rem" }}>
              {item.description}
            </p>
            <div style={{ display: "flex", gap: "1rem", fontSize: "0.8rem", color: "#666" }}>
              <span>Created: {formatDate(item.created_at)}</span>
              <span>Closed: {formatDate(item.closed_at)}</span>
            </div>
          </div>
          <div style={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.4rem" }}>
            <span
              style={{
                fontSize: "0.7rem",
                fontWeight: "bold",
                padding: "2px 8px",
                borderRadius: "3px",
                background: statusColor(item.status) + "22",
                color: statusColor(item.status),
              }}
            >
              {statusLabel(item.status)}
            </span>
            <div>
              <span style={{ fontSize: "0.7rem", color: "#94a3b8", display: "block", marginBottom: "2px" }}>
                freshness at close
              </span>
              <FreshnessBar value={item.freshness_at_close} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function RemindersPage() {
  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <Link href="/" style={{ color: "#4a9eff", textDecoration: "none", fontSize: "0.875rem" }}>
        ← back
      </Link>
      <h1 style={{ fontSize: "1.25rem", fontWeight: "bold", margin: "1rem 0 0.25rem 0" }}>
        Reminder History
      </h1>
      <p style={{ color: "#666", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
        Past assistant actions. Freshness at close shows how timely the resolution was.
      </p>
      {/* @ts-expect-error async server component */}
      <ReminderFeed userId="" />
    </main>
  );
}
