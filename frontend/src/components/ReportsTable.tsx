import type { Report } from '../api'

export function ReportsTable({ reports }: { reports: Report[] }) {
  const rows = [...reports].reverse()

  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#161b22] shadow-lg">
      <div className="px-4 pt-3">
        <h2 className="text-sm font-semibold">Verlauf</h2>
      </div>
      <div className="max-h-[40vh] overflow-auto px-1 pb-2 pt-2">
        {rows.length === 0 ? (
          <div className="p-6 text-center text-sm text-[#8b949e]">Noch keine Reports vorhanden.</div>
        ) : (
          <table className="w-full border-collapse text-[0.83rem]">
            <thead>
              <tr className="text-[0.72rem] uppercase tracking-wide text-[#8b949e]">
                <th className="px-3 py-1.5 text-left">Zeit</th>
                <th className="px-3 py-1.5 text-left">Lat</th>
                <th className="px-3 py-1.5 text-left">Lon</th>
                <th className="px-3 py-1.5 text-left">Genauigkeit</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-white/5 hover:bg-white/5">
                  <td className="whitespace-nowrap px-3 py-1.5">{new Date(r.timestamp).toLocaleString()}</td>
                  <td className="whitespace-nowrap px-3 py-1.5">{r.lat.toFixed(5)}</td>
                  <td className="whitespace-nowrap px-3 py-1.5">{r.lon.toFixed(5)}</td>
                  <td className="whitespace-nowrap px-3 py-1.5">{r.accuracy ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
