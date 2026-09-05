import { useCallback, useEffect, useState } from 'react'
import type { Airtag, Report, Status } from './api'
import { getAirtags, getReports, getStatus } from './api'
import { Header } from './components/Header'
import { StatCards } from './components/StatCards'
import { MapCard } from './components/MapCard'
import { ReportsTable } from './components/ReportsTable'
import { AirtagManager } from './components/AirtagManager'

export default function App() {
  const [airtags, setAirtags] = useState<Airtag[] | null>(null)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [status, setStatus] = useState<Status | null>(null)
  const [managerOpen, setManagerOpen] = useState(false)

  const refreshAirtags = useCallback(async () => {
    const list = await getAirtags()
    setAirtags(list)
    setCurrentId((prev) => (prev && list.some((a) => a.id === prev) ? prev : (list[0]?.id ?? null)))
    return list
  }, [])

  useEffect(() => {
    refreshAirtags()
  }, [refreshAirtags])

  useEffect(() => {
    if (!currentId) {
      setReports([])
      setStatus(null)
      return
    }
    let cancelled = false
    Promise.all([getReports(currentId), getStatus(currentId)]).then(([r, s]) => {
      if (!cancelled) {
        setReports(r)
        setStatus(s)
      }
    })
    return () => {
      cancelled = true
    }
  }, [currentId])

  const title = status ? `AirTagSentry — ${status.airtag_name}` : 'AirTagSentry'
  useEffect(() => {
    document.title = title
  }, [title])

  return (
    <div className="min-h-screen pb-[env(safe-area-inset-bottom)]">
      <Header
        title={title}
        airtags={airtags ?? []}
        currentId={currentId}
        onSelect={setCurrentId}
        onOpenManager={() => setManagerOpen(true)}
      />

      <main className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
        {airtags !== null && airtags.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-[#161b22] p-8 text-center text-sm text-[#8b949e]">
            Noch kein AirTag konfiguriert.{' '}
            <button
              type="button"
              className="text-[#58a6ff] underline underline-offset-2"
              onClick={() => setManagerOpen(true)}
            >
              Jetzt eines hinzufügen
            </button>
            .
          </div>
        ) : (
          <>
            {status && <StatCards status={status} />}
            <MapCard reports={reports} />
            <ReportsTable reports={reports} />
          </>
        )}
      </main>

      {managerOpen && (
        <AirtagManager
          onClose={() => setManagerOpen(false)}
          onChanged={async () => {
            const list = await refreshAirtags()
            const id = list.some((a) => a.id === currentId) ? currentId : (list[0]?.id ?? null)
            if (id) {
              const [r, s] = await Promise.all([getReports(id), getStatus(id)])
              setReports(r)
              setStatus(s)
            } else {
              setReports([])
              setStatus(null)
            }
          }}
        />
      )}
    </div>
  )
}
