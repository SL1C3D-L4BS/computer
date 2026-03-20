import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Computer — Operations',
  description: 'Computer Cyber-Physical Operations Console',
};

export default function HomePage() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="border-b border-zinc-800 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-mono font-semibold tracking-tight">COMPUTER</span>
          <span className="text-xs text-zinc-500 font-mono">OPS</span>
        </div>
        <nav className="flex gap-6 text-sm text-zinc-400">
          <Link href="/jobs" className="hover:text-zinc-100 transition-colors">Jobs</Link>
          <Link href="/assets" className="hover:text-zinc-100 transition-colors">Assets</Link>
          <Link href="/incidents" className="hover:text-zinc-100 transition-colors">Incidents</Link>
          <Link href="/approvals" className="hover:text-zinc-100 transition-colors">Approvals</Link>
        </nav>
      </div>

      <div className="px-8 py-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatusCard title="System" status="loading" />
        <StatusCard title="Orchestrator" status="loading" />
        <StatusCard title="MQTT" status="loading" />
      </div>

      <div className="px-8">
        <h2 className="text-sm font-mono text-zinc-500 uppercase tracking-widest mb-4">Recent Jobs</h2>
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
          <div className="px-6 py-8 text-center text-zinc-600 text-sm">
            No jobs yet. Submit a job via the API or ops console.
          </div>
        </div>
      </div>
    </main>
  );
}

function StatusCard({ title, status }: { title: string; status: 'ok' | 'degraded' | 'down' | 'loading' }) {
  const statusColors = {
    ok: 'text-emerald-400',
    degraded: 'text-amber-400',
    down: 'text-red-400',
    loading: 'text-zinc-600',
  };

  const statusLabels = {
    ok: 'Online',
    degraded: 'Degraded',
    down: 'Offline',
    loading: 'Checking...',
  };

  return (
    <div className="border border-zinc-800 rounded-lg px-5 py-4 bg-zinc-900/50">
      <div className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">{title}</div>
      <div className={`text-sm font-mono ${statusColors[status]}`}>{statusLabels[status]}</div>
    </div>
  );
}
