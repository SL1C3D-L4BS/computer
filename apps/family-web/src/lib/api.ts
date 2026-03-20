/**
 * family-web API client — fetches from runtime-kernel GET /state
 * and proxied surfaces for approvals and history.
 *
 * V4 upgrade: offline-aware fetch using stale-while-revalidate pattern.
 *
 * SCOPE DISCIPLINE (local-first-sync-strategy.md):
 * - offlineFetch(): shopping, chores, reminders, approvals cache, dashboard snapshots
 * - requiresNetwork(): work memory, site state, approval submissions, personal memory
 *
 * Reference: docs/architecture/local-first-sync-strategy.md | ADR-035
 */

const KERNEL_URL = process.env.NEXT_PUBLIC_KERNEL_URL ?? "http://localhost:8100";

// ── In-memory stale cache for offline-aware fetch ──────────────────────────
// In production, replace with PGlite-backed cache.
const _staleCache = new Map<string, { data: unknown; cachedAt: number }>();
const STALE_TTL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Stale-while-revalidate fetch for in-scope offline data.
 *
 * If the network request fails and we have a cached value, returns the cache
 * with a stale indicator. Only safe for the scoped data types (shopping,
 * chores, reminders, approvals cache, dashboard snapshots).
 */
async function offlineFetch<T>(
  cacheKey: string,
  fetcher: () => Promise<T>
): Promise<{ data: T; stale: boolean }> {
  // Try network first
  try {
    const data = await fetcher();
    _staleCache.set(cacheKey, { data, cachedAt: Date.now() });
    return { data, stale: false };
  } catch {
    // Network failed — try stale cache
    const cached = _staleCache.get(cacheKey);
    if (cached) {
      const ageMs = Date.now() - cached.cachedAt;
      return { data: cached.data as T, stale: ageMs > STALE_TTL_MS };
    }
    throw new Error(`Network unavailable and no cached data for ${cacheKey}`);
  }
}

/**
 * Network-required fetch for out-of-scope data (work memory, site state,
 * approval submissions). Throws immediately if offline — no fallback.
 */
async function requiresNetwork<T>(fetcher: () => Promise<T>): Promise<T> {
  if (typeof window !== "undefined" && !navigator.onLine) {
    throw new Error(
      "This operation requires network access and is not available offline."
    );
  }
  return fetcher();
}

export interface ReminderHistoryItem {
  id: string;
  description: string;
  status: "CLOSED" | "ABANDONED" | "CANCELLED";
  created_at: string;
  closed_at: string | null;
  user_id: string;
  priority_score: number;
  freshness_at_close: number;
}

export interface PendingApproval {
  id: string;
  description: string;
  user_id: string;
  due_at: string | null;
  priority_score: number;
  created_at: string;
  workflow_id: string | null;
  risk_class?: string;
}

export interface HouseholdDashboardData {
  mode_by_surface: Record<string, string>;
  active_workflow_ids: string[];
  active_emergency: boolean;
  attention_load: number;
  system_health_flags: string[];
  open_loops_count: number;
  pending_commitments_count: number;
  follow_up_queue_count: number;
}

export async function fetchComputerState() {
  const res = await fetch(`${KERNEL_URL}/state`, {
    next: { revalidate: 10 },
  });
  if (!res.ok) throw new Error(`kernel /state failed: ${res.status}`);
  return res.json();
}

/**
 * Offline-aware household dashboard snapshot.
 * Returns stale snapshot when offline; indicates staleness to caller.
 */
export async function fetchHouseholdDashboardOfflineAware(): Promise<{
  data: HouseholdDashboardData;
  stale: boolean;
}> {
  return offlineFetch("household_dashboard", fetchHouseholdDashboard);
}

/**
 * Offline-aware pending approvals list (read-only cache).
 * Approvals cannot be submitted offline — only viewed.
 */
export async function fetchPendingApprovalsOfflineAware(userId: string): Promise<{
  data: PendingApproval[];
  stale: boolean;
}> {
  return offlineFetch(`pending_approvals:${userId}`, () => fetchPendingApprovals(userId));
}

export async function fetchReminderHistory(userId: string): Promise<ReminderHistoryItem[]> {
  const state = await fetchComputerState();
  // Filter open_loops that are closed or abandoned (history items)
  const loops = (state.open_loops ?? []) as Array<{
    id: string;
    description: string;
    status: string;
    created_at: string;
    closed_at: string | null;
    user_id: string;
    priority_score: number;
    freshness: number;
  }>;
  return loops
    .filter((l) => ["CLOSED", "ABANDONED", "CANCELLED"].includes(l.status))
    .filter((l) => !userId || l.user_id === userId)
    .map((l) => ({
      id: l.id,
      description: l.description,
      status: l.status as ReminderHistoryItem["status"],
      created_at: l.created_at,
      closed_at: l.closed_at,
      user_id: l.user_id,
      priority_score: l.priority_score,
      freshness_at_close: l.freshness,
    }));
}

export async function fetchPendingApprovals(userId: string): Promise<PendingApproval[]> {
  const state = await fetchComputerState();
  const commitments = (state.pending_commitments ?? []) as Array<{
    id: string;
    description: string;
    user_id: string;
    due_at: string | null;
    priority_score: number;
    created_at: string;
    workflow_id: string | null;
    status: string;
  }>;
  return commitments
    .filter((c) => c.status === "PENDING")
    .filter((c) => !userId || c.user_id === userId);
}

export async function fetchHouseholdDashboard(): Promise<HouseholdDashboardData> {
  const state = await fetchComputerState();
  return {
    mode_by_surface: state.mode_by_surface ?? {},
    active_workflow_ids: state.active_workflow_ids ?? [],
    active_emergency: state.active_emergency ?? false,
    attention_load: state.attention_load ?? 0,
    system_health_flags: state.system_health_flags ?? [],
    open_loops_count: (state.open_loops ?? []).filter(
      (l: { status: string }) => l.status === "ACTIVE"
    ).length,
    pending_commitments_count: (state.pending_commitments ?? []).filter(
      (c: { status: string }) => c.status === "PENDING"
    ).length,
    follow_up_queue_count: (state.follow_up_queue ?? []).filter(
      (f: { status: string }) => f.status === "PENDING"
    ).length,
  };
}

export async function approveCommitment(commitmentId: string, approverId: string) {
  // Approval requires approval-track auth (passkey re-auth) and network.
  // This is a requiresNetwork operation — no offline fallback.
  return requiresNetwork(async () => {
    const res = await fetch(`${KERNEL_URL}/commitments/${commitmentId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approver_id: approverId }),
    });
    if (!res.ok) throw new Error(`approval failed: ${res.status}`);
    return res.json();
  });
}
