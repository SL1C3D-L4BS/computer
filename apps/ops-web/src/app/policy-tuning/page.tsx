"use client";

/**
 * Policy Tuning Console — Parameter Table
 *
 * Stub page: shows all tunable parameters, edit controls,
 * and impact report filing.
 *
 * Hard invariant: publish requires PolicyImpactReport + replay + passkey re-auth.
 * Reference: docs/product/policy-tuning-console.md | docs/delivery/policy-publish-gate.md
 * ADR-036
 */

import { useState } from "react";

interface TunableParameter {
  name: string;
  domain: string;
  currentValue: string | number;
  description: string;
  impactReportFiled: boolean;
}

const TUNABLE_PARAMETERS: TunableParameter[] = [
  {
    name: "attention.interrupt_net_value_threshold",
    domain: "Attention",
    currentValue: 0.0,
    description: "Minimum net_value required to trigger INTERRUPT decision",
    impactReportFiled: false,
  },
  {
    name: "attention.suppression_cooldown_s",
    domain: "Attention",
    currentValue: 300,
    description: "Cooldown (seconds) after suppression before re-interrupt allowed",
    impactReportFiled: false,
  },
  {
    name: "attention.urgency_decay_rate",
    domain: "Attention",
    currentValue: 0.1,
    description: "Exponential urgency decay rate over time",
    impactReportFiled: false,
  },
  {
    name: "confidence.min_decision_threshold",
    domain: "Confidence",
    currentValue: 0.65,
    description: "Minimum confidence before abstaining and asking clarification",
    impactReportFiled: false,
  },
  {
    name: "loops.decay_rate",
    domain: "Memory",
    currentValue: 0.03,
    description: "Exponential decay rate for loop freshness",
    impactReportFiled: false,
  },
  {
    name: "routing.voice_length_budget_personal",
    domain: "Voice",
    currentValue: 2,
    description: "Max sentences in PERSONAL mode voice response",
    impactReportFiled: false,
  },
];

export default function PolicyTuningPage() {
  const [params, setParams] = useState(TUNABLE_PARAMETERS);
  const [editingParam, setEditingParam] = useState<string | null>(null);
  const [proposedValue, setProposedValue] = useState<string>("");
  const [showImpactForm, setShowImpactForm] = useState<string | null>(null);

  function startEdit(paramName: string, currentVal: string | number) {
    setEditingParam(paramName);
    setProposedValue(String(currentVal));
  }

  function fileImpactReport(paramName: string) {
    setShowImpactForm(paramName);
  }

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px", fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Policy Tuning Console</h1>
      <p style={{ color: "#666", fontSize: 13, marginBottom: 24 }}>
        Every parameter change requires a{" "}
        <strong>PolicyImpactReport + replay + passkey re-auth</strong> before publishing.
        See{" "}
        <a href="/docs/policy-publish-gate" style={{ color: "#1a1a1a" }}>
          policy-publish-gate.md
        </a>
        .
      </p>

      <div style={{ border: "1px solid #e0e0e0", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f5f5f5" }}>
              {["Parameter", "Domain", "Current Value", "Status", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {params.map((p, i) => (
              <tr key={p.name} style={{ borderTop: "1px solid #eee", background: i % 2 === 0 ? "#fff" : "#fafafa" }}>
                <td style={{ padding: "10px 16px" }}>
                  <code style={{ fontSize: 11 }}>{p.name}</code>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>{p.description}</div>
                </td>
                <td style={{ padding: "10px 16px", color: "#555" }}>{p.domain}</td>
                <td style={{ padding: "10px 16px" }}>
                  <strong>{p.currentValue}</strong>
                </td>
                <td style={{ padding: "10px 16px" }}>
                  {p.impactReportFiled ? (
                    <span style={{ color: "#137333", fontSize: 12 }}>✓ Impact report filed</span>
                  ) : (
                    <span style={{ color: "#888", fontSize: 12 }}>No pending change</span>
                  )}
                </td>
                <td style={{ padding: "10px 16px" }}>
                  <button
                    onClick={() => startEdit(p.name, p.currentValue)}
                    style={{
                      padding: "4px 10px", fontSize: 12, marginRight: 6,
                      background: "#1a1a1a", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
                    }}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => fileImpactReport(p.name)}
                    style={{
                      padding: "4px 10px", fontSize: 12,
                      background: "#f5f5f5", color: "#333", border: "1px solid #ccc",
                      borderRadius: 4, cursor: "pointer",
                    }}
                  >
                    File Impact Report
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 24, padding: "12px 16px", background: "#fff3cd", borderRadius: 6, fontSize: 13 }}>
        <strong>Publish is blocked</strong> until impact report filed, replay complete, and passkey re-auth done.
        Navigate to{" "}
        <a href="/policy-tuning/simulate" style={{ color: "#1a1a1a" }}>Replay Viewer</a>{" "}
        after filing impact report.
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
        <a href="/policy-tuning/simulate" style={{ padding: "10px 16px", background: "#1a1a1a", color: "#fff", borderRadius: 6, fontSize: 13, textDecoration: "none" }}>
          → Replay Viewer
        </a>
        <a href="/policy-tuning/history" style={{ padding: "10px 16px", background: "#f5f5f5", color: "#333", border: "1px solid #ccc", borderRadius: 6, fontSize: 13, textDecoration: "none" }}>
          → Change History
        </a>
      </div>
    </main>
  );
}
