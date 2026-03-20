"use client";

/**
 * Policy Tuning Console — Replay Viewer (What-If Simulation)
 *
 * Stub: runs a PolicyImpactReport through the replay API,
 * compares outcomes, displays divergence table.
 *
 * Hard gate: PolicyImpactReport must exist BEFORE replay begins.
 * Hard gate: replay must complete BEFORE publish is enabled.
 * Reference: docs/delivery/policy-publish-gate.md | ADR-036
 */

import { useState } from "react";

interface ReplayResult {
  traceId: string;
  baselineDecision: string;
  candidateDecision: string;
  diverged: boolean;
  confidenceDelta: number;
}

const STUB_RESULTS: ReplayResult[] = [
  { traceId: "tr-a1b2", baselineDecision: "INTERRUPT", candidateDecision: "INTERRUPT", diverged: false, confidenceDelta: 0.02 },
  { traceId: "tr-c3d4", baselineDecision: "DEFER", candidateDecision: "INTERRUPT", diverged: true, confidenceDelta: -0.08 },
  { traceId: "tr-e5f6", baselineDecision: "SUPPRESS", candidateDecision: "SUPPRESS", diverged: false, confidenceDelta: 0.00 },
  { traceId: "tr-g7h8", baselineDecision: "INTERRUPT", candidateDecision: "DEFER", diverged: true, confidenceDelta: -0.15 },
  { traceId: "tr-i9j0", baselineDecision: "DEFER", candidateDecision: "DEFER", diverged: false, confidenceDelta: 0.01 },
];

export default function SimulatePage() {
  const [ran, setRan] = useState(false);
  const [running, setRunning] = useState(false);
  const [impactReportId, setImpactReportId] = useState("");

  function runReplay() {
    if (!impactReportId.trim()) {
      alert("You must enter the PolicyImpactReport ID before running replay.");
      return;
    }
    setRunning(true);
    setTimeout(() => {
      setRunning(false);
      setRan(true);
    }, 1500);
  }

  const divergences = STUB_RESULTS.filter((r) => r.diverged);
  const divergenceRate = ran ? (divergences.length / STUB_RESULTS.length) * 100 : null;
  const publishBlocked = ran && divergenceRate !== null && divergenceRate > 20;

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px", fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Replay Viewer — What-If Simulation</h1>
      <p style={{ color: "#666", fontSize: 13, marginBottom: 24 }}>
        Runs recent traces against the candidate policy. Requires a filed{" "}
        <strong>PolicyImpactReport ID</strong>. Publish is blocked until replay passes.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", marginBottom: 24 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
            PolicyImpactReport ID *
          </label>
          <input
            type="text"
            placeholder="pir-xxxxxxxx"
            value={impactReportId}
            onChange={(e) => setImpactReportId(e.target.value)}
            style={{ width: "100%", padding: "8px 12px", border: "1px solid #ccc", borderRadius: 4, fontSize: 13 }}
          />
        </div>
        <button
          onClick={runReplay}
          disabled={running}
          style={{
            padding: "9px 20px", background: "#1a1a1a", color: "#fff",
            border: "none", borderRadius: 4, cursor: "pointer", fontSize: 13,
          }}
        >
          {running ? "Running…" : "Run Replay"}
        </button>
      </div>

      {ran && (
        <>
          <div style={{
            display: "flex", gap: 16, marginBottom: 20,
          }}>
            {[
              { label: "Traces Replayed", value: STUB_RESULTS.length },
              { label: "Divergences", value: divergences.length },
              { label: "Divergence Rate", value: `${divergenceRate?.toFixed(1)}%` },
              { label: "Publish Gate", value: publishBlocked ? "BLOCKED" : "PASS" },
            ].map((s) => (
              <div key={s.label} style={{
                flex: 1, padding: "12px 16px", border: "1px solid #e0e0e0",
                borderRadius: 6, textAlign: "center",
              }}>
                <div style={{ fontSize: 11, color: "#888", marginBottom: 4 }}>{s.label}</div>
                <div style={{
                  fontSize: 20, fontWeight: 700,
                  color: s.label === "Publish Gate" ? (publishBlocked ? "#c62828" : "#137333") : "#1a1a1a",
                }}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          <div style={{ border: "1px solid #e0e0e0", borderRadius: 8, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f5f5f5" }}>
                  {["Trace ID", "Baseline", "Candidate", "Conf Δ", "Diverged"].map((h) => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STUB_RESULTS.map((r, i) => (
                  <tr key={r.traceId} style={{
                    borderTop: "1px solid #eee",
                    background: r.diverged ? "#fff3e0" : (i % 2 === 0 ? "#fff" : "#fafafa"),
                  }}>
                    <td style={{ padding: "10px 16px" }}><code style={{ fontSize: 11 }}>{r.traceId}</code></td>
                    <td style={{ padding: "10px 16px" }}>{r.baselineDecision}</td>
                    <td style={{ padding: "10px 16px" }}>{r.candidateDecision}</td>
                    <td style={{ padding: "10px 16px", color: r.confidenceDelta < 0 ? "#c62828" : "#137333" }}>
                      {r.confidenceDelta >= 0 ? "+" : ""}{r.confidenceDelta.toFixed(2)}
                    </td>
                    <td style={{ padding: "10px 16px" }}>
                      {r.diverged
                        ? <span style={{ color: "#c62828", fontWeight: 600 }}>✗ YES</span>
                        : <span style={{ color: "#137333" }}>✓ no</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {publishBlocked ? (
            <div style={{ marginTop: 20, padding: "12px 16px", background: "#ffebee", borderRadius: 6, fontSize: 13 }}>
              <strong>Publish blocked:</strong> divergence rate {divergenceRate?.toFixed(1)}% exceeds 20% threshold.
              Revisit the parameter change or file a new PolicyImpactReport with revised expectations.
            </div>
          ) : (
            <div style={{ marginTop: 20, padding: "12px 16px", background: "#e8f5e9", borderRadius: 6, fontSize: 13 }}>
              <strong>Replay passed.</strong> Divergence rate within threshold.
              You may proceed to passkey re-auth and publish.
            </div>
          )}
        </>
      )}
    </main>
  );
}
