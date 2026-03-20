/**
 * Surface 3: Household State Dashboard
 *
 * Shows: active workflows, current modes per surface, system health flags,
 * open loop counts, attention load, emergency status.
 *
 * This is the accountability surface for system state — not a control panel.
 * Read-only; polling every 30s in production via ISR.
 *
 * Data source: ComputerState (GET /state on runtime-kernel)
 * Reference: docs/architecture/system-state-model.md
 */
import Link from "next/link";
import { fetchHouseholdDashboard, type HouseholdDashboardData } from "@/lib/api";

export const dynamic = "force-dynamic";

function AttentionBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value < 0.4 ? "#22c55e" : value < 0.7 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <div style={{ height: "8px", width: "100px", background: "#f0f0f0", borderRadius: "4px", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontSize: "0.8rem", color }}>{pct}%</span>
    </div>
  );
}

function ModeTag({ mode }: { mode: string }) {
  const colors: Record<string, string> = {
    PERSONAL: "#4a9eff",
    FAMILY: "#a855f7",
    WORK: "#f59e0b",
    SITE: "#22c55e",
    EMERGENCY: "#ef4444",
  };
  const color = colors[mode] ?? "#94a3b8";
  return (
    <span style={{ fontSize: "0.7rem", fontWeight: "bold", padding: "2px 8px", borderRadius: "3px", background: color + "22", color }}>
      {mode}
    </span>
  );
}

async function Dashboard() {
  let data: HouseholdDashboardData | null = null;
  let error: string | null = null;

  try {
    data = await fetchHouseholdDashboard();
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load dashboard";
  }

  if (error) {
    return (
      <div style={{ padding: "1rem", background: "#fff3f3", border: "1px solid #fca5a5", borderRadius: "6px", color: "#dc2626", fontSize: "0.875rem" }}>
        Could not connect to runtime-kernel: {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Emergency Banner */}
      {data.active_emergency && (
        <div style={{ padding: "1rem", background: "#fef2f2", border: "2px solid #ef4444", borderRadius: "6px", color: "#dc2626", fontWeight: "bold" }}>
          ⚠ EMERGENCY MODE ACTIVE
        </div>
      )}

      {/* Health Flags */}
      {data.system_health_flags.length > 0 && (
        <div style={{ padding: "0.75rem", background: "#fffbeb", border: "1px solid #f59e0b", borderRadius: "6px", fontSize: "0.875rem" }}>
          <strong>System flags:</strong>{" "}
          {data.system_health_flags.map((f) => (
            <span key={f} style={{ marginRight: "0.5rem", color: "#b45309" }}>{f}</span>
          ))}
        </div>
      )}

      {/* Stats Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem" }}>
        <StatCard label="Open Loops" value={data.open_loops_count} color={data.open_loops_count > 10 ? "#f59e0b" : "#22c55e"} />
        <StatCard label="Pending Commitments" value={data.pending_commitments_count} color={data.pending_commitments_count > 5 ? "#f59e0b" : "#22c55e"} />
        <StatCard label="Follow-ups" value={data.follow_up_queue_count} color="#4a9eff" />
      </div>

      {/* Attention Load */}
      <div style={{ padding: "1rem", border: "1px solid #e0e0e0", borderRadius: "6px" }}>
        <strong style={{ fontSize: "0.875rem" }}>Attention Load</strong>
        <div style={{ marginTop: "0.5rem" }}>
          <AttentionBar value={data.attention_load} />
        </div>
        <p style={{ margin: "0.4rem 0 0", fontSize: "0.75rem", color: "#666" }}>
          Higher load reduces interrupt threshold. Values above 70% suppress non-critical alerts.
        </p>
      </div>

      {/* Active Workflows */}
      <div style={{ padding: "1rem", border: "1px solid #e0e0e0", borderRadius: "6px" }}>
        <strong style={{ fontSize: "0.875rem" }}>Active Workflows ({data.active_workflow_ids.length})</strong>
        {data.active_workflow_ids.length === 0 ? (
          <p style={{ margin: "0.5rem 0 0", color: "#94a3b8", fontSize: "0.875rem", fontStyle: "italic" }}>
            No active workflows
          </p>
        ) : (
          <ul style={{ margin: "0.5rem 0 0", padding: 0, listStyle: "none", fontSize: "0.8rem", color: "#4b5563" }}>
            {data.active_workflow_ids.map((id) => (
              <li key={id} style={{ padding: "4px 0", borderBottom: "1px solid #f3f4f6" }}>
                <code>{id}</code>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Modes by Surface */}
      <div style={{ padding: "1rem", border: "1px solid #e0e0e0", borderRadius: "6px" }}>
        <strong style={{ fontSize: "0.875rem" }}>Modes by Surface</strong>
        {Object.keys(data.mode_by_surface).length === 0 ? (
          <p style={{ margin: "0.5rem 0 0", color: "#94a3b8", fontSize: "0.875rem", fontStyle: "italic" }}>
            No active surfaces
          </p>
        ) : (
          <div style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {Object.entries(data.mode_by_surface).map(([surface, mode]) => (
              <div key={surface} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.8rem" }}>
                <code style={{ color: "#4b5563" }}>{surface}</code>
                <ModeTag mode={mode} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ padding: "1rem", border: "1px solid #e0e0e0", borderRadius: "6px", textAlign: "center" }}>
      <div style={{ fontSize: "1.75rem", fontWeight: "bold", color }}>{value}</div>
      <div style={{ fontSize: "0.75rem", color: "#666", marginTop: "0.25rem" }}>{label}</div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <Link href="/" style={{ color: "#4a9eff", textDecoration: "none", fontSize: "0.875rem" }}>
        ← back
      </Link>
      <h1 style={{ fontSize: "1.25rem", fontWeight: "bold", margin: "1rem 0 0.25rem 0" }}>
        Household State Dashboard
      </h1>
      <p style={{ color: "#666", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
        Live snapshot from runtime-kernel. Read-only.
      </p>
      {/* @ts-expect-error async server component */}
      <Dashboard />
    </main>
  );
}
