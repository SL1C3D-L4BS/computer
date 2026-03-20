"use client";

/**
 * Passkey Registration Page — family-web
 *
 * Implements WebAuthn registration ceremony for the session track.
 * On success, writes OpenFGA tuple: device:<device_id> trusted_by user:<user_id>
 *
 * Reference: docs/architecture/passkey-auth-strategy.md | ADR-034
 */

import { useState } from "react";

const IDENTITY_SERVICE_URL =
  process.env.NEXT_PUBLIC_IDENTITY_SERVICE_URL ?? "http://localhost:9000";

interface RegistrationState {
  status: "idle" | "pending" | "success" | "error";
  message: string;
  credentialId?: string;
}

async function beginRegistration(userId: string): Promise<PublicKeyCredentialCreationOptions> {
  const res = await fetch(`${IDENTITY_SERVICE_URL}/identity/passkey/register/begin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error(`Registration begin failed: ${res.status}`);
  const json = await res.json();
  // Decode base64url challenge and user.id for WebAuthn API
  json.challenge = base64urlDecode(json.challenge);
  json.user.id = base64urlDecode(json.user.id);
  return json as PublicKeyCredentialCreationOptions;
}

async function completeRegistration(
  userId: string,
  credential: PublicKeyCredential
): Promise<{ credential_id: string; device_id: string }> {
  const attestation = credential.response as AuthenticatorAttestationResponse;
  const payload = {
    user_id: userId,
    id: credential.id,
    raw_id: base64urlEncode(credential.rawId),
    response: {
      client_data_json: base64urlEncode(attestation.clientDataJSON),
      attestation_object: base64urlEncode(attestation.attestationObject),
    },
    type: credential.type,
  };
  const res = await fetch(`${IDENTITY_SERVICE_URL}/identity/passkey/register/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Registration complete failed: ${res.status}`);
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

export default function RegisterPage() {
  const [userId, setUserId] = useState("");
  const [state, setState] = useState<RegistrationState>({ status: "idle", message: "" });

  async function handleRegister() {
    if (!userId.trim()) {
      setState({ status: "error", message: "User ID is required." });
      return;
    }
    setState({ status: "pending", message: "Starting passkey registration…" });
    try {
      const options = await beginRegistration(userId);
      const credential = await navigator.credentials.create({ publicKey: options });
      if (!credential) throw new Error("No credential returned from browser");
      const result = await completeRegistration(userId, credential as PublicKeyCredential);
      setState({
        status: "success",
        message: "Passkey registered successfully.",
        credentialId: result.credential_id,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setState({ status: "error", message: msg });
    }
  }

  return (
    <main style={{ maxWidth: 480, margin: "80px auto", fontFamily: "system-ui", padding: "0 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Register Passkey</h1>
      <p style={{ color: "#555", marginBottom: 24, fontSize: 14 }}>
        Passkeys provide phishing-resistant authentication. Your passkey is stored on this device
        and never leaves it.
      </p>

      <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>
        User ID
      </label>
      <input
        type="text"
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        placeholder="your-username"
        style={{
          width: "100%", padding: "10px 12px", fontSize: 16,
          border: "1px solid #ccc", borderRadius: 6, marginBottom: 16, boxSizing: "border-box",
        }}
      />

      <button
        onClick={handleRegister}
        disabled={state.status === "pending"}
        style={{
          width: "100%", padding: "12px", fontSize: 16, fontWeight: 600,
          background: state.status === "pending" ? "#999" : "#1a1a1a",
          color: "#fff", border: "none", borderRadius: 6, cursor: "pointer",
        }}
      >
        {state.status === "pending" ? "Registering…" : "Register Passkey"}
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
          {state.credentialId && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#555" }}>
              Credential: {state.credentialId}
            </div>
          )}
        </div>
      )}

      <p style={{ marginTop: 24, fontSize: 12, color: "#888" }}>
        Already registered?{" "}
        <a href="/auth/login" style={{ color: "#1a1a1a" }}>Sign in with passkey</a>
      </p>
    </main>
  );
}
