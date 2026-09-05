import type { Status } from '../api'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function StatCards({ status }: { status: Status }) {
  return (
    <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="rounded-2xl border border-white/10 bg-[#161b22] p-4">
        <div className="text-[0.72rem] uppercase tracking-wide text-[#8b949e]">Letzter Report</div>
        <div className="mt-1 text-sm font-semibold">
          {status.last_report ? formatDate(status.last_report.timestamp) : 'Noch keine Reports'}
        </div>
      </div>
      <div className="rounded-2xl border border-white/10 bg-[#161b22] p-4">
        <div className="text-[0.72rem] uppercase tracking-wide text-[#8b949e]">Polling-Intervall</div>
        <div className="mt-1 text-sm font-semibold">alle {status.poll_interval_minutes} min</div>
      </div>
      <div
        className={`rounded-2xl border p-4 ${
          status.last_alert ? 'border-[#9a6700]' : 'border-white/10'
        } bg-[#161b22]`}
      >
        <div className="text-[0.72rem] uppercase tracking-wide text-[#8b949e]">Letzter Alarm</div>
        <div className="mt-1 text-sm font-semibold">
          {status.last_alert
            ? `${status.last_alert.reason} · ${formatDate(status.last_alert.timestamp)}`
            : 'Keiner'}
        </div>
      </div>
    </section>
  )
}
