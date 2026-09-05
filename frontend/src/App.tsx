import { useCallback, useEffect, useState } from 'react'
import type { Airtag, Report, Status } from './api'
import { createAirtag, getAirtags, getReports, getStatus } from './api'
import { AirtagList } from './components/AirtagList'
import { AirtagDetail } from './components/AirtagDetail'
import { MapCard } from './components/MapCard'
import { SettingsPanel } from './components/SettingsPanel'
import { TabBar } from './components/TabBar'
import type { TabKey } from './components/TabBar'
import { usePushNotifications } from './hooks/usePushNotifications'

export default function App() {
  const [airtags, setAirtags] = useState<Airtag[]>([])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [statuses, setStatuses] = useState<Record<string, Status>>({})
  const [reports, setReports] = useState<Report[]>([])
  const [activeTab, setActiveTab] = useState<TabKey>('objects')
  const [showDetail, setShowDetail] = useState(false)
  const [sheetExpanded, setSheetExpanded] = useState(false)
  const push = usePushNotifications()

  const refreshAirtags = useCallback(async () => {
    const list = await getAirtags()
    setAirtags(list)
    setCurrentId((prev) => (prev && list.some((a) => a.id === prev) ? prev : (list[0]?.id ?? null)))

    const entries = await Promise.all(
      list.map(async (a) => {
        try {
          return [a.id, await getStatus(a.id)] as const
        } catch {
          return null
        }
      }),
    )
    const nextStatuses: Record<string, Status> = {}
    for (const entry of entries) {
      if (entry) nextStatuses[entry[0]] = entry[1]
    }
    setStatuses(nextStatuses)
    return list
  }, [])

  useEffect(() => {
    refreshAirtags()
  }, [refreshAirtags])

  useEffect(() => {
    if (!currentId) {
      setReports([])
      return
    }
    let cancelled = false
    getReports(currentId).then((r) => {
      if (!cancelled) setReports(r)
    })
    return () => {
      cancelled = true
    }
  }, [currentId])

  const currentAirtag = airtags.find((a) => a.id === currentId) ?? null
  const title = currentAirtag ? `AirTagSentry — ${currentAirtag.name}` : 'AirTagSentry'
  useEffect(() => {
    document.title = title
  }, [title])

  function handleSelect(id: string) {
    setCurrentId(id)
    setShowDetail(true)
  }

  async function handleCreate(name: string) {
    const created = await createAirtag(name)
    await refreshAirtags()
    handleSelect(created.id)
  }

  return (
    <div className="relative h-screen w-full overflow-hidden bg-[var(--bg)] md:flex">
      {/* isolate: Leaflet's internal panes use z-index up to 700 (markers,
          popups); without a stacking context scoped here, those values
          escape this wrapper and paint over the sheet below despite DOM
          order and the sheet's own z-10. */}
      <div className="absolute inset-0 isolate md:relative md:flex-1">
        <MapCard reports={reports} />
      </div>

      {/* Sheet + tab bar, grouped so the tab bar always sits directly below
          the sheet: on mobile this column is pinned to the screen's bottom
          edge and only the sheet's height changes (collapsed/expanded), so
          the tab bar never moves; on desktop it's simply the static
          sidebar column. */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col md:static md:h-full md:w-[360px] md:shrink-0 md:border-r md:border-[var(--divider)]">
        <div
          className="sheet flex flex-col overflow-hidden rounded-t-2xl bg-[var(--bg)] shadow-[0_-8px_30px_rgba(0,0,0,0.5)] md:h-auto md:flex-1 md:rounded-none md:shadow-none"
          data-expanded={sheetExpanded}
        >
          <button
            type="button"
            onClick={() => setSheetExpanded((v) => !v)}
            aria-expanded={sheetExpanded}
            aria-label={sheetExpanded ? 'Ansicht verkleinern' : 'Ansicht auf Vollbild vergrößern'}
            className="flex shrink-0 justify-center py-2 md:hidden"
          >
            <span className="h-1 w-9 rounded-full bg-[var(--divider)]" />
          </button>
          <div className="min-h-0 flex-1">
            {activeTab === 'settings' ? (
              <SettingsPanel />
            ) : showDetail && currentAirtag ? (
              <AirtagDetail
                airtag={currentAirtag}
                status={statuses[currentAirtag.id] ?? null}
                reports={reports}
                onBack={() => setShowDetail(false)}
                onChanged={async () => {
                  await refreshAirtags()
                }}
                onDeleted={async () => {
                  await refreshAirtags()
                  setShowDetail(false)
                }}
                pushStatus={push.status}
                onEnablePush={push.enable}
              />
            ) : (
              <AirtagList
                airtags={airtags}
                statuses={statuses}
                currentId={currentId}
                onSelect={handleSelect}
                onCreate={handleCreate}
                pushStatus={push.status}
                onEnablePush={push.enable}
              />
            )}
          </div>
        </div>
        <TabBar active={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  )
}
