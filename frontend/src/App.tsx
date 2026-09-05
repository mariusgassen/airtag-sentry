import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { Airtag, Report, Status } from './api'
import { createAirtag, getAirtags, getReports, getStatus } from './api'
import { AirtagList } from './components/AirtagList'
import { AirtagDetail } from './components/AirtagDetail'
import { MapCard } from './components/MapCard'
import { OverviewMap } from './components/OverviewMap'
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
  const sheetRef = useRef<HTMLDivElement>(null)
  const dragStartY = useRef(0)
  const dragStartExpanded = useRef(false)
  const dragHandledClick = useRef(false)

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
    setActiveTab('objects')
  }

  async function handleCreate(name: string) {
    const created = await createAirtag(name)
    await refreshAirtags()
    handleSelect(created.id)
  }

  // The grab handle used to only support a tap (setSheetExpanded toggle) -
  // it looked draggable but wasn't. This drives a live height preview via
  // the --drag-delta CSS var (see index.css) while dragging, and resolves
  // to a collapsed/expanded snap on release; a real click (e.g. keyboard
  // activation, which never fires these pointer events) still just toggles.
  const CLICK_THRESHOLD_PX = 6
  const SNAP_THRESHOLD_PX = 40

  function handleHandlePointerDown(e: ReactPointerEvent<HTMLButtonElement>) {
    e.currentTarget.setPointerCapture(e.pointerId)
    dragStartY.current = e.clientY
    dragStartExpanded.current = sheetExpanded
    if (sheetRef.current) sheetRef.current.dataset.dragging = 'true'
  }

  function handleHandlePointerMove(e: ReactPointerEvent<HTMLButtonElement>) {
    const sheet = sheetRef.current
    if (!sheet || sheet.dataset.dragging !== 'true') return
    const delta = dragStartY.current - e.clientY
    const clamped = Math.max(-window.innerHeight, Math.min(window.innerHeight, delta))
    sheet.style.setProperty('--drag-delta', `${clamped}px`)
  }

  function handleHandlePointerUp(e: ReactPointerEvent<HTMLButtonElement>) {
    const sheet = sheetRef.current
    if (!sheet) return
    const delta = dragStartY.current - e.clientY
    sheet.dataset.dragging = 'false'
    sheet.style.removeProperty('--drag-delta')

    const wasExpanded = dragStartExpanded.current
    let nextExpanded = wasExpanded
    if (Math.abs(delta) < CLICK_THRESHOLD_PX) {
      nextExpanded = !wasExpanded
    } else if (!wasExpanded && delta > SNAP_THRESHOLD_PX) {
      nextExpanded = true
    } else if (wasExpanded && -delta > SNAP_THRESHOLD_PX) {
      nextExpanded = false
    }
    dragHandledClick.current = true
    setSheetExpanded(nextExpanded)
  }

  function handleHandlePointerCancel() {
    const sheet = sheetRef.current
    if (!sheet) return
    sheet.dataset.dragging = 'false'
    sheet.style.removeProperty('--drag-delta')
  }

  function handleHandleClick() {
    // Pointer interactions already resolved the toggle in
    // handleHandlePointerUp and this click is the synthetic one that
    // follows it - swallow it once. A click with no preceding pointerup
    // (keyboard/switch-control activation) still toggles normally.
    if (dragHandledClick.current) {
      dragHandledClick.current = false
      return
    }
    setSheetExpanded((v) => !v)
  }

  return (
    // fixed+inset-0 rather than h-[100dvh]: in an installed iOS home-screen
    // PWA, 100dvh has not reliably spanned the true edge-to-edge screen
    // across WebKit versions, leaving the bottom-pinned sheet/tab-bar column
    // short of the real bottom and exposing a gap above the home indicator.
    // A fixed element's viewport (with viewport-fit=cover, set in
    // index.html) is spec-guaranteed to cover the true physical screen.
    <div className="fixed inset-0 overflow-hidden bg-[var(--bg)] md:flex">
      {/* isolate: Leaflet's internal panes use z-index up to 700 (markers,
          popups); without a stacking context scoped here, those values
          escape this wrapper and paint over the sheet below despite DOM
          order and the sheet's own z-10. */}
      <div className="absolute inset-0 isolate md:relative md:flex-1">
        {activeTab === 'objects' && showDetail && currentAirtag ? (
          <MapCard reports={reports} airtagId={currentAirtag.id} />
        ) : (
          <OverviewMap airtags={airtags} statuses={statuses} onSelect={handleSelect} />
        )}
      </div>

      {/* Sheet + tab bar, grouped so the tab bar always sits directly below
          the sheet: on mobile this column is pinned to the screen's bottom
          edge and only the sheet's height changes (collapsed/expanded), so
          the tab bar never moves; on desktop it's simply the static
          sidebar column. */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col md:static md:h-full md:w-[360px] md:shrink-0 md:border-r md:border-[var(--divider)]">
        <div
          ref={sheetRef}
          className="sheet flex flex-col overflow-hidden rounded-t-2xl bg-[var(--bg)] shadow-[0_-8px_30px_rgba(0,0,0,0.5)] md:h-auto md:flex-1 md:rounded-none md:shadow-none"
          data-expanded={sheetExpanded}
        >
          <button
            type="button"
            onPointerDown={handleHandlePointerDown}
            onPointerMove={handleHandlePointerMove}
            onPointerUp={handleHandlePointerUp}
            onPointerCancel={handleHandlePointerCancel}
            onClick={handleHandleClick}
            aria-expanded={sheetExpanded}
            aria-label={sheetExpanded ? 'Ansicht verkleinern' : 'Ansicht auf Vollbild vergrößern'}
            className="chrome-blur flex shrink-0 touch-none justify-center py-2 md:hidden"
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
