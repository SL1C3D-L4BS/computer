"""
MCP November 2025 Stable Spec — OAuth 2.1 Authorization Flow

Implements:
- RFC 9728 (Protected Resource Metadata Discovery)
- RFC 8414 (AS Metadata)
- OpenID Connect Discovery (/.well-known/openid-configuration)
- PKCE OAuth 2.1 (RFC 7636, required by OAuth 2.1)
- RFC 8707 (Token Audience Binding)
- Incremental scope consent: on 403 with insufficient_scope, re-initiate
  OAuth with narrowed scope set
- URL-mode elicitation: when MCP server returns elicitation/create with
  type:url, route through attention-engine and pass url field in
  AttentionDecision.metadata

Reference: docs/architecture/tool-fabric-and-mcp-plan.md
ADR: ADR-018 (Tool Fabric Plane)
"""
from __future__ import annotations

import hashlib
import os
import urllib.parse
from dataclasses import dataclass, field

import httpx
import structlog

log = structlog.get_logger(__name__)


@dataclass
class MCPAuthContext:
    """Result of a successful MCP OAuth 2.1 token validation."""
    subject: str         # User or service identifier
    audience: str        # Must match this gateway's resource URI (RFC 8707)
    scopes: list[str]    # Granted scopes
    tier_claim: str      # Custom claim: tool trust tier (T0-T4)
    raw_token: str
    oidc_claims: dict = field(default_factory=dict)  # Claims from OIDC ID token if present


@dataclass
class DiscoveredAuthServer:
    """Authorization server discovered via RFC 9728 → RFC 8414 → OIDC."""
    resource_uri: str             # RFC 9728: protected resource URI
    authorization_server: str     # RFC 8414: AS issuer
    token_endpoint: str           # RFC 8414: token_endpoint
    authorization_endpoint: str   # RFC 8414: authorization_endpoint
    pkce_required: bool = True    # RFC 9728: require PKCE
    # OIDC extensions (November 2025 stable spec)
    oidc_issuer: str = ""         # OIDC discovery issuer (if OIDC-capable AS)
    userinfo_endpoint: str = ""   # OIDC userinfo endpoint
    scopes_supported: list[str] = field(default_factory=list)


@dataclass
class ElicitationRequest:
    """
    MCP elicitation/create payload (November 2025 stable spec).
    When type='url', route through attention-engine; pass url in AttentionDecision.metadata.
    """
    elicitation_id: str
    elicitation_type: str   # "url" | "text" | "choice"
    url: str | None = None  # Present when type="url"
    prompt: str = ""
    required: bool = False


async def discover_auth_server(resource_uri: str) -> DiscoveredAuthServer | None:
    """
    MCP November 2025: Multi-step discovery chain.

    1. RFC 9728: GET {resource_uri}/.well-known/oauth-protected-resource
    2. RFC 8414: GET {as_issuer}/.well-known/oauth-authorization-server
    3. OIDC:    GET {as_issuer}/.well-known/openid-configuration (if available)

    OIDC discovery is attempted alongside RFC 8414; failures are non-fatal.
    """
    well_known_url = f"{resource_uri}/.well-known/oauth-protected-resource"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Step 1: RFC 9728 — discover which AS protects this resource
            r = await client.get(well_known_url)
            if r.status_code != 200:
                log.warning("mcp_auth.discovery_failed", url=well_known_url, status=r.status_code)
                return None

            resource_metadata = r.json()
            as_issuer = resource_metadata.get("authorization_servers", [None])[0]
            if not as_issuer:
                log.warning("mcp_auth.no_as_in_resource_metadata", url=well_known_url)
                return None

            # Step 2: RFC 8414 — discover AS metadata
            as_metadata_url = f"{as_issuer}/.well-known/oauth-authorization-server"
            r2 = await client.get(as_metadata_url)
            if r2.status_code != 200:
                log.warning("mcp_auth.as_discovery_failed", url=as_metadata_url)
                return None

            as_metadata = r2.json()
            discovered = DiscoveredAuthServer(
                resource_uri=resource_uri,
                authorization_server=as_issuer,
                token_endpoint=as_metadata.get("token_endpoint", ""),
                authorization_endpoint=as_metadata.get("authorization_endpoint", ""),
                scopes_supported=as_metadata.get("scopes_supported", []),
                pkce_required=True,
            )

            # Step 3: OIDC Discovery — attempt alongside RFC 8414 (non-fatal)
            oidc_url = f"{as_issuer}/.well-known/openid-configuration"
            try:
                r3 = await client.get(oidc_url)
                if r3.status_code == 200:
                    oidc_meta = r3.json()
                    discovered.oidc_issuer = oidc_meta.get("issuer", as_issuer)
                    discovered.userinfo_endpoint = oidc_meta.get("userinfo_endpoint", "")
                    # Merge OIDC scopes into supported list
                    oidc_scopes = oidc_meta.get("scopes_supported", [])
                    discovered.scopes_supported = list(
                        set(discovered.scopes_supported) | set(oidc_scopes)
                    )
                    log.info("mcp_auth.oidc_discovery_success", issuer=discovered.oidc_issuer)
                else:
                    log.debug("mcp_auth.oidc_not_available", url=oidc_url, status=r3.status_code)
            except Exception as e:
                log.debug("mcp_auth.oidc_discovery_skipped", reason=str(e))

            return discovered

        except Exception as e:
            log.warning("mcp_auth.discovery_error", error=str(e))
            return None


def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code verifier + challenge (RFC 7636, required by OAuth 2.1).
    Returns: (code_verifier, code_challenge)
    """
    code_verifier = urllib.parse.quote(os.urandom(40).hex())
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    import base64
    code_challenge_b64 = base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()
    return code_verifier, code_challenge_b64


def validate_token_audience(token_payload: dict, expected_resource_uri: str) -> bool:
    """
    RFC 8707: Token Audience Binding.
    The token's 'aud' claim must match the resource server's URI.
    This prevents token replay across different resource servers.
    """
    aud = token_payload.get("aud", [])
    if isinstance(aud, str):
        aud = [aud]
    return expected_resource_uri in aud


async def handle_incremental_scope_consent(
    response_status: int,
    response_body: dict,
    auth_server: DiscoveredAuthServer,
    current_scopes: list[str],
) -> list[str] | None:
    """
    MCP November 2025: Incremental scope consent.

    On 403 with insufficient_scope error, compute the minimal additional
    scope set needed and re-initiate OAuth flow with narrowed scope.
    Returns the narrowed scope list to request, or None if not applicable.

    Caller is responsible for re-initiating the OAuth flow with the returned scopes.
    """
    if response_status != 403:
        return None
    error = response_body.get("error", "")
    if error != "insufficient_scope":
        return None

    required_scope = response_body.get("scope", "")
    if not required_scope:
        return None

    required_scopes = set(required_scope.split())
    current_set = set(current_scopes)
    missing = required_scopes - current_set

    if not missing:
        log.warning("mcp_auth.scope_error_but_scopes_present",
                    required=required_scope, current=current_scopes)
        return None

    # Narrowed scope: existing + only the missing scopes needed for this request
    narrowed = sorted(current_set | missing)
    log.info("mcp_auth.incremental_scope_consent",
             missing=sorted(missing), narrowed=narrowed)
    return narrowed


def handle_url_elicitation(elicitation: ElicitationRequest) -> dict:
    """
    MCP November 2025: URL-mode elicitation.

    When the MCP server returns elicitation/create with type='url', this
    function prepares the payload to route through the attention-engine.
    The url field must be passed in AttentionDecision.metadata so the
    operator surface can present it appropriately.

    Returns an AttentionDecision.metadata-compatible dict.
    """
    if elicitation.elicitation_type != "url":
        return {}

    metadata = {
        "elicitation_id":   elicitation.elicitation_id,
        "elicitation_type": "url",
        "url":              elicitation.url,
        "prompt":           elicitation.prompt,
        "required":         elicitation.required,
        "route_to":         "attention_engine",
        "attention_action": "INTERRUPT" if elicitation.required else "DIGEST",
    }
    log.info("mcp_auth.url_elicitation_routed",
             elicitation_id=elicitation.elicitation_id,
             url=elicitation.url,
             required=elicitation.required)
    return metadata


async def validate_bearer_token(
    token: str,
    resource_uri: str,
) -> MCPAuthContext | None:
    """
    Validate a Bearer token against the MCP resource server's authorization server.

    Steps:
    1. Parse token (in prod: JWT validation with AS public key)
    2. Validate audience binding (RFC 8707)
    3. Return MCPAuthContext if valid

    Status: STUB — returns a synthetic context for development.
    Replace with real JWT validation before deploying to site network.
    """
    # Stub: in development mode, accept a known dev token
    dev_tokens = {
        "dev-token": MCPAuthContext(
            subject="system",
            audience=resource_uri,
            scopes=["tools:T0", "tools:T1", "tools:T2", "tools:T3", "tools:T4"],
            tier_claim="T4",
            raw_token=token,
        ),
    }

    if token in dev_tokens:
        log.info("mcp_auth.stub_token_accepted", subject=dev_tokens[token].subject)
        return dev_tokens[token]

    # In production: parse JWT, validate signature with AS public key,
    # validate audience (RFC 8707), validate scopes.
    log.warning("mcp_auth.token_not_recognized", token_prefix=token[:8] + "...")
    return None
