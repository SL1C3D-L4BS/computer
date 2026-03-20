"use client";

/**
 * Policy Tuning Console — Change History
 *
 * Immutable audit trail of all published policy changes.
 * Each entry records: parameter, old → new, filed by, replay pass,
 * passkey re-auth confirmation, and publish timestamp.
 *
 * Reference: docs/delivery/policy-publish-gate.md | ADR-036
 */

const STUB_HISTORY = [
  {
    id: "pch-001",
    parameter: "attention.interrupt_net_value_threshold",
    oldValue: "-0.2",
    newValue: "0.0",
    filedBy: "founder",
    replayDivergenceRate: "12.0%",
    passkeReauthAt: "2026-03-10T09:15:00Z",
    publishedAt: "2026-03-10T09:16:44Z",
    status: "PUBLISHED",
  },
  {
    id: "pch-002",
    parameter: "confidence.min_decision_threshold",
    oldValue: "0.60",
    newValue: "0.65",
    filedBy: "founder",
    replayDivergenceRate: "8.0%",
    passkeReauthAt: "2026-03-14T14:22:10Z",
    publishedAt: "2026-03-14T14:24:05Z",
    status: "PUBLISHED",
  },
  {
    id: "pch-003",
    parameter: "attention.suppression_cooldown_s",
    oldValue: "600",
    newValue: "300",
    filedBy: "founder",
    replayDivergenceRate: "22.0%",
    passkeReauthAt: "N/A",
    publishedAt: "N/A",
    status: "BLOCKED",
  },
];

export default function PolicyHistoryPage() {
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Policy Change History</h1>
      <p style={{ color: "#666", fontSize: 13, marginBottom: 24 }}>
        Immutable audit trail. Every published change must have: PolicyImpactReport → replay pass → passkey re-auth.
      </p>

      <div style={{ border: "1px solid #e0e0e0", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f5f5f5" }}>
              {["ID", "Parameter", "Old → New", "Filed By", "Replay Rate", "Passkey Re-auth", "Published At", "Status"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {STUB_HISTORY.map((entry, i) => (
              <tr key={entry.id} style={{
                borderTop: "1px solid #eee",
                background: entry.status === "BLOCKED" ? "#fff3e0" : (i % 2 === 0 ? "#fff" : "#fafafa"),
              }}>
                <td style={{ padding: "10px 14px" }}><code style={{ fontSize: 11 }}>{entry.id}</code></td>
                <td style={{ padding: "10px 14px" }}><code style={{ fontSize: 11 }}>{entry.parameter}</code></td>
                <td style={{ padding: "10px 14px", fontFamily: "monospace" }}>
                  {entry.oldValue} → {entry.newValue}
                </td>
                <td style={{ padding: "10px 14px" }}>{entry.filedBy}</td>
                <td style={{ padding: "10px 14px" }}>{entry.replayDivergenceRate}</td>
                <td style={{ padding: "10px 14px", fontSize: 11, color: "#555" }}>
                  {entry.passkeReauthAt}
                </td>
                <td style={{ padding: "10px 14px", fontSize: 11, color: "#555" }}>
                  {entry.publishedAt}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  {entry.status === "PUBLISHED" ? (
                    <span style={{ color: "#137333", fontWeight: 600, fontSize: 12 }}>✓ PUBLISHED</span>
                  ) : (
                    <span style={{ color: "#c62828", fontWeight: 600, fontSize: 12 }}>✗ BLOCKED</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 20, display: "flex", gap: 12 }}>
        <a href="/policy-tuning" style={{ padding: "10px 16px", background: "#f5f5f5", color: "#333", border: "1px solid #ccc", borderRadius: 6, fontSize: 13, textDecoration: "none" }}>
          ← Parameters
        </a>
        <a href="/policy-tuning/simulate" style={{ padding: "10px 16px", background: "#1a1a1a", color: "#fff", borderRadius: 6, fontSize: 13, textDecoration: "none" }}>
          → Replay Viewer
        </a>
      </div>
    </main>
  );
}
