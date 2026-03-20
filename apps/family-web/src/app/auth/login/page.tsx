"use client";

/**
 * Passkey Login Page — family-web
 *
 * Implements WebAuthn authentication ceremony for the session track.
 * On success, sets HttpOnly session cookie via identity-service.
 *
 * For approval-track re-auth, see: docs/architecture/passkey-auth-strategy.md
 * Reference: ADR-034
 */

import { useState } from "react";

const IDENTITY_SERVICE_URL =
  process.env.NEXT_PUBLIC_IDENTITY_SERVICE_URL ?? "http://localhost:9000";

interface LoginState {
  status: "idle" | "pending" | "success" | "error";
  message: string;
}

async function beginAuthentication(userId?: string): Promise<PublicKeyCredentialRequestOptions> {
  const res = await fetch(`${IDENTITY_SERVICE_URL}/identity/passkey/auth/begin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId ?? null }),
  });
  if (!res.ok) throw new Error(`Auth begin failed: ${res.status}`);
  const json = await res.json();
  json.challenge = base64urlDecode(json.challenge);
  if (json.allowCredentials) {
    json.allowCredentials = json.allowCredentials.map((c: { id: string; type: string }) => ({
      ...c,
      id: base64urlDecode(c.id),
    }));
  }
  return json as PublicKeyCredentialRequestOptions;
}

async function completeAuthentication(
  credential: PublicKeyCredential
): Promise<{ session_token: string; expires_at: string; user_id: string }> {
  const assertion = credential.response as AuthenticatorAssertionResponse;
  const payload = {
    id: credential.id,
    raw_id: base64urlEncode(credential.rawId),
    response: {
      client_data_json: base64urlEncode(assertion.clientDataJSON),
      authenticator_data: base64urlEncode(assertion.authenticatorData),
      signature: base64urlEncode(assertion.signature),
      user_handle: assertion.userHandle ? base64urlEncode(assertion.userHandle) : null,
    },
    type: credential.type,
  };
  const res = await fetch(`${IDENTITY_SERVICE_URL}/identity/passkey/auth/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",  // Allow HttpOnly cookie to be set
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Auth complete failed: ${res.status}`);
  return res.json();
}

function base64urlDecode(str: string): ArrayBuffer {
  const base64 = str.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

export default function LoginPage() {
  const [userId, setUserId] = useState("");
  const [state, setState] = useState<LoginState>({ status: "idle", message: "" });

  async function handleLogin() {
    setState({ status: "pending", message: "Waiting for passkey…" });
    try {
      const options = await beginAuthentication(userId.trim() || undefined);
      const credential = await navigator.credentials.get({ publicKey: options });
      if (!credential) throw new Error("No credential returned from browser");
      const result = await completeAuthentication(credential as PublicKeyCredential);
      setState({
        status: "success",
        message: `Signed in as ${result.user_id}. Session valid until ${new Date(result.expires_at).toLocaleString()}.`,
      });
      // In production: redirect to /dashboard or the intended page
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setState({ status: "error", message: msg });
    }
  }

  return (
    <main style={{ maxWidth: 480, margin: "80px auto", fontFamily: "system-ui", padding: "0 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Sign In</h1>
      <p style={{ color: "#555", marginBottom: 24, fontSize: 14 }}>
        Use your registered passkey to sign in. No password required.
      </p>

      <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>
        User ID <span style={{ fontWeight: 400, color: "#888" }}>(optional)</span>
      </label>
      <input
        type="text"
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        placeholder="Leave blank to discover passkeys automatically"
        style={{
          width: "100%", padding: "10px 12px", fontSize: 14,
          border: "1px solid #ccc", borderRadius: 6, marginBottom: 16, boxSizing: "border-box",
        }}
      />

      <button
        onClick={handleLogin}
        disabled={state.status === "pending"}
        style={{
          width: "100%", padding: "12px", fontSize: 16, fontWeight: 600,
          background: state.status === "pending" ? "#999" : "#1a1a1a",
          color: "#fff", border: "none", borderRadius: 6, cursor: "pointer",
        }}
      >
        {state.status === "pending" ? "Waiting for passkey…" : "Sign In with Passkey"}
      </button>

      {state.message && (
        <div
          style={{
            marginTop: 16, padding: "12px 16px", borderRadius: 6, fontSize: 14,
            background: state.status === "success" ? "#e6f4ea" : state.status === "error" ? "#fce8e6" : "#f5f5f5",
            color: state.status === "success" ? "#137333" : state.status === "error" ? "#c5221f" : "#333",
          }}
        >
          {state.message}
        </div>
      )}

      <div style={{ marginTop: 24, padding: "12px 16px", background: "#f8f8f8", borderRadius: 6, fontSize: 12 }}>
        <strong>Approval track:</strong> Some actions (policy changes, memory export, sensitive approvals)
        require passkey re-authentication even when signed in. This is by design — see{" "}
        <a href="/docs/passkey-strategy" style={{ color: "#1a1a1a" }}>passkey-auth-strategy</a>.
      </div>

      <p style={{ marginTop: 16, fontSize: 12, color: "#888" }}>
        New device?{" "}
        <a href="/auth/register" style={{ color: "#1a1a1a" }}>Register a passkey</a>
      </p>
    </main>
  );
}
