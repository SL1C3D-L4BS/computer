/**
 * family-web Root — V3 household intelligence surfaces
 *
 * Three surfaces:
 * 1. /reminders  — Reminder/history feed (closed + abandoned loops)
 * 2. /approvals  — Pending approvals awaiting family confirmation
 * 3. /dashboard  — Household state: active workflows, current mode, system health
 */
import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ fontFamily: "monospace", padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: "bold", marginBottom: "0.5rem" }}>
        Computer — Family
      </h1>
      <p style={{ color: "#666", marginBottom: "2rem", fontSize: "0.9rem" }}>
        Household intelligence surfaces. Read-only status + approval actions.
      </p>

      <nav style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <SurfaceCard
          href="/reminders"
          title="Reminder History"
          description="Past assistant actions, completed reminders, and abandoned loops."
          badge="history"
        />
        <SurfaceCard
          href="/approvals"
          title="Pending Approvals"
          description="Items awaiting family confirmation before proceeding."
          badge="action"
        />
        <SurfaceCard
          href="/dashboard"
          title="Household State"
          description="Active workflows, current modes, system health, open loops."
          badge="monitor"
        />
      </nav>
    </main>
  );
}

function SurfaceCard({
  href,
  title,
  description,
  badge,
}: {
  href: string;
  title: string;
  description: string;
  badge: string;
}) {
  const badgeColors: Record<string, string> = {
    history: "#4a9eff",
    action: "#ff6b35",
    monitor: "#22c55e",
  };

  return (
    <Link
      href={href}
      style={{
        display: "block",
        padding: "1.25rem",
        border: "1px solid #e0e0e0",
        borderRadius: "6px",
        textDecoration: "none",
        color: "inherit",
        transition: "border-color 0.15s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
        <span
          style={{
            fontSize: "0.7rem",
            fontWeight: "bold",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            padding: "2px 8px",
            borderRadius: "3px",
            background: badgeColors[badge] + "22",
            color: badgeColors[badge],
          }}
        >
          {badge}
        </span>
        <strong style={{ fontSize: "1rem" }}>{title}</strong>
      </div>
      <p style={{ margin: 0, color: "#666", fontSize: "0.875rem" }}>{description}</p>
    </Link>
  );
}
