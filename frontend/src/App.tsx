import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { Airtag, OwnerLocation, Report, Status } from './api'
import {
  createAirtag,
  getAirtags,
  getOwnerAppleStatus,
  getOwnerDeviceHistory,
  getOwnerDeviceLocations,
  getReports,
  getStatus,
} from './api'
import { AirtagList } from './components/AirtagList'
import { AirtagDetail } from './components/AirtagDetail'
import { MapCard } from './components/MapCard'
import { OverviewMap } from './components/OverviewMap'
import { SettingsPanel } from './components/SettingsPanel'
import { TabBar } from './components/TabBar'
import type { TabKey } from './components/TabBar'
import { usePushNotifications } from './hooks/usePushNotifications'

// 'default' is the normal half-height sheet; 'expanded' is near-fullscreen
// (leaving a peek of map above, see index.css); 'minimized' shrinks the
// sheet to just its grab handle so the map behind it is fully visible.
// Transitions only ever move one step at a time - see resolveNextSheetState.
type SheetState = 'minimized' | 'default' | 'expanded'

const CLICK_THRESHOLD_PX = 6
const SNAP_THRESHOLD_PX = 40

// Drag/tap gesture resolution for the sheet's grab handle, kept pure and
// outside the component so the transition table is easy to read/test in
// isolation. `delta` is dragStartY - pointerUp.clientY (positive = dragged
// up/toward expand). A tap (tiny delta) always resolves to a single
// deterministic step; a drag past the threshold moves exactly one level -
// expanded and minimized are never reached directly from one another.
function resolveNextSheetState(start: SheetState, delta: number): SheetState {
  if (Math.abs(delta) < CLICK_THRESHOLD_PX) {
    return start === 'default' ? 'expanded' : 'default'
  }
  if (delta > SNAP_THRESHOLD_PX) {
    return start === 'minimized' ? 'default' : 'expanded'
  }
  if (delta < -SNAP_THRESHOLD_PX) {
    return start === 'expanded' ? 'default' : 'minimized'
  }
  return start
}

export default function App() {
  const [airtags, setAirtags] = useState<Airtag[]>([])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [statuses, setStatuses] = useState<Record<string, Status>>({})
  const [reports, setReports] = useState<Report[]>([])
  // Current position of every *enabled* owner device (Settings -> Eigene
  // Geräte) - shown as markers on the map. The *primary* one among them
  // additionally drives away-correlation display and the trail below.
  const [ownerLocations, setOwnerLocations] = useState<OwnerLocation[]>([])
  const [primaryLocationHistory, setPrimaryLocationHistory] = useState<OwnerLocation[]>([])
  const [ownerConnected, setOwnerConnected] = useState(false)
  const [ownerDeviceId, setOwnerDeviceId] = useState<string | null>(null)
  const [ownerDeviceName, setOwnerDeviceName] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('objects')
  const [showDetail, setShowDetail] = useState(false)
  const [sheetState, setSheetState] = useState<SheetState>('default')
  const push = usePushNotifications()
  const sheetRef = useRef<HTMLDivElement>(null)
  const dragStartY = useRef(0)
  const dragStartState = useRef<SheetState>('default')
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
    getOwnerDeviceLocations()
      .then(setOwnerLocations)
      .catch(() => setOwnerLocations([]))
    getOwnerAppleStatus()
      .then((s) => {
        setOwnerConnected(s.connected)
        setOwnerDeviceId(s.primary_device_id ?? null)
        setOwnerDeviceName(s.primary_device_name ?? null)
      })
      .catch(() => {
        setOwnerConnected(false)
        setOwnerDeviceId(null)
        setOwnerDeviceName(null)
      })
  }, [])

  useEffect(() => {
    if (!ownerDeviceId) {
      setPrimaryLocationHistory([])
      return
    }
    getOwnerDeviceHistory(ownerDeviceId)
      .then(setPrimaryLocationHistory)
      .catch(() => setPrimaryLocationHistory([]))
  }, [ownerDeviceId])

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
  const ownerLocation = ownerLocations.find((l) => l.device_id === ownerDeviceId) ?? null
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

  // The grab handle used to only support a tap (setSheetState toggle) - it
  // looked draggable but wasn't. This drives a live height preview via the
  // --drag-delta CSS var (see index.css) while dragging, and resolves to a
  // minimized/default/expanded snap on release (see resolveNextSheetState);
  // a real click (e.g. keyboard activation, which never fires these pointer
  // events) still just resolves the same tap rule directly.
  function handleHandlePointerDown(e: ReactPointerEvent<HTMLButtonElement>) {
    e.currentTarget.setPointerCapture(e.pointerId)
    dragStartY.current = e.clientY
    dragStartState.current = sheetState
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

    dragHandledClick.current = true
    setSheetState(resolveNextSheetState(dragStartState.current, delta))
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
    setSheetState((s) => (s === 'default' ? 'expanded' : 'default'))
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
          <MapCard
            reports={reports}
            airtag={currentAirtag}
            ownerLocations={ownerLocations}
            primaryLocationHistory={primaryLocationHistory}
          />
        ) : (
          <OverviewMap
            airtags={airtags}
            statuses={statuses}
            onSelect={handleSelect}
            ownerLocations={ownerLocations}
            primaryLocationHistory={primaryLocationHistory}
          />
        )}
      </div>

      {/* Title bar for the reserved top safe area. index.html's
          status-bar-style comment covers why this space can't be
          translucent map instead (CLAUDE.md's "iOS status bar" section has
          the full trade-off) - this leans into that constraint instead of
          fighting it, the same way most non-immersive iOS apps use a real
          header rather than trying to bleed content under the status bar.
          Positioned starting at safe-area-inset-top (not top-0): iOS
          reserves the strip above that for its own opaque status bar
          regardless of what's drawn there, so a title placed any higher
          would just be covered. .leaflet-top's mobile-only offset (see
          index.css) adds --header-h on top of its existing
          safe-area-inset-top push so the zoom control clears this bar
          instead of sitting underneath it. Currently just the selected
          AirTag's name (or "AirTags" with none selected/on the overview
          map) - reusing the same fallback as `title` above - but the slot
          is deliberately generic so future per-AirTag meta (e.g. battery,
          last-seen) can go here without a layout change. */}
      <div className="pointer-events-none absolute inset-x-0 top-[env(safe-area-inset-top)] z-10 flex h-[var(--header-h)] items-center justify-center border-b border-[var(--divider)] chrome-blur md:hidden">
        <span className="truncate px-12 text-[15px] font-semibold text-[var(--text)]">
          {currentAirtag?.name ?? 'AirTags'}
        </span>
      </div>

      {/* Sheet + tab bar, grouped so the tab bar always sits directly below
          the sheet: on mobile this column is pinned to the screen's bottom
          edge and only the sheet's height changes (collapsed/expanded), so
          the tab bar never moves; on desktop it's simply the static
          sidebar column.
          inset-0 (not bottom-0 + intrinsic height) so this column's own box
          is pinned to the fixed root exactly like the map pane above - the
          same guarantee that made the root itself fixed+inset-0 rather than
          h-[100dvh] (see that comment). A bottom-0-and-auto-height column
          only reaches the map's true edge if the browser's dynamic-viewport
          math for an intrinsic-height box agrees with the math it used for
          the map's own inset-0 box; on some WebKit/PWA combinations it
          doesn't, leaving a sliver of raw map exposed below the tab bar
          with no glass. pointer-events-none + justify-end so the empty
          space this now reserves above the sheet still passes clicks
          through to the map, restored to auto on the two real children. */}
      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col justify-end md:pointer-events-auto md:static md:h-full md:w-[360px] md:shrink-0 md:border-r md:border-[var(--divider)]">
        <div
          ref={sheetRef}
          className="sheet pointer-events-auto flex flex-col overflow-hidden rounded-t-2xl bg-[var(--bg)] shadow-[0_-8px_30px_rgba(0,0,0,0.5)] md:h-auto md:flex-1 md:rounded-none md:shadow-none"
          data-state={sheetState}
        >
          <button
            type="button"
            onPointerDown={handleHandlePointerDown}
            onPointerMove={handleHandlePointerMove}
            onPointerUp={handleHandlePointerUp}
            onPointerCancel={handleHandlePointerCancel}
            onClick={handleHandleClick}
            aria-expanded={sheetState === 'expanded'}
            aria-label={
              sheetState === 'expanded'
                ? 'Ansicht verkleinern'
                : sheetState === 'minimized'
                  ? 'Ansicht einblenden'
                  : 'Ansicht auf Vollbild vergrößern'
            }
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
                ownerConnected={ownerConnected}
                ownerLocation={ownerLocation}
                ownerDeviceName={ownerDeviceName}
              />
            )}
          </div>
        </div>
        <TabBar active={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  )
}
