import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type {
  AppSettings,
  Airtag,
  LocationHistory,
  LocationStay,
  OwnerDevice,
  OwnerLocation,
  Place,
  Report,
  ReportStay,
  Status,
  TimelineVisit,
} from './api'
import { setColorPalette } from './airtagColor'
import { setCartoApiKey, setMapTileProvider } from './mapTiles'
import {
  createAirtag,
  getAirtags,
  getCartoStatus,
  getOwnerAppleStatus,
  getOwnerDeviceHistory,
  getOwnerDeviceLocations,
  getOwnerDevices,
  getPlaces,
  getReports,
  getSettings,
  getStatus,
  getTimeline,
  ping,
  pollNow,
  reorderAirtags,
  reorderOwnerDevices,
} from './api'
import { deviceLabel } from './format'
import { ObjectsList } from './components/ObjectsList'
import { AirtagDetail } from './components/AirtagDetail'
import { DeviceDetail } from './components/DeviceDetail'
import { DeviceMapCard } from './components/DeviceMapCard'
import { ChevronDownIcon, ChevronUpIcon } from './components/icons'
import { MapCard } from './components/MapCard'
import { OverviewMap } from './components/OverviewMap'
import { SettingsPanel } from './components/SettingsPanel'
import type { PlaceSeed } from './components/SettingsPlaces'
import { TabBar } from './components/TabBar'
import type { TabKey } from './components/TabBar'
import { TimelinePage } from './components/TimelinePage'
import type { TimelineFilter, TimelineRange } from './components/TimelinePage'
import { usePushNotifications } from './hooks/usePushNotifications'

// 'default' is the normal half-height sheet; 'expanded' is near-fullscreen
// (leaving a peek of map above, see index.css); 'minimized' shrinks the
// sheet to just its grab handle so the map behind it is fully visible.
// Transitions only ever move one step at a time - see resolveNextSheetState.
type SheetState = 'minimized' | 'default' | 'expanded'

const CLICK_THRESHOLD_PX = 6
const SNAP_THRESHOLD_PX = 40

// How often the whole app re-fetches from the DB in the background, so a
// new poller fix (tracker.py) or a change made elsewhere (e.g. a device
// toggled in Settings -> Apple-Konten, which keeps its own local state -
// see OwnerDevicesPanel.tsx) shows up here without a manual reload. Reads
// are cheap (plain Postgres selects, no live Apple calls), so this is
// independent of - and much shorter than - the user-configurable
// polling_interval_minutes that gates actual Apple polling.
const AUTO_REFRESH_MS = 20_000

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
  const [reportStays, setReportStays] = useState<ReportStay[]>([])
  // Current position of every *enabled* owner device (Settings -> Eigene
  // Geräte) - shown as markers on the map, each with its own trail below.
  // The *primary* one among them additionally drives away-correlation
  // display (the "Du" row / evaluate_away on the backend).
  const [ownerLocations, setOwnerLocations] = useState<OwnerLocation[]>([])
  const [ownerLocationHistories, setOwnerLocationHistories] = useState<Record<string, OwnerLocation[]>>({})
  // Keyed by device_id, mirroring ownerLocationHistories.
  const [ownerLocationStays, setOwnerLocationStays] = useState<Record<string, LocationStay[]>>({})
  const [ownerConnected, setOwnerConnected] = useState(false)
  // True once a background refresh (see AUTO_REFRESH_MS's effect below) has
  // failed to reach the server at all - drives the offline banner. Distinct
  // from any single endpoint returning an error (a normal ApiError): this is
  // specifically "the request never got a response," which apiFetch's own
  // per-call timeout (api.ts) guarantees resolves within a bounded time
  // instead of hanging forever.
  const [offline, setOffline] = useState(false)
  const [manualRefreshing, setManualRefreshing] = useState(false)
  // Only used to read back color_palette - fetched here (not just inside
  // SettingsPanel) so a saved palette change applies app-wide without a
  // manual reload, same as any other background refresh (see AUTO_REFRESH_MS).
  const [settings, setSettings] = useState<AppSettings | null>(null)
  // Applied synchronously during render (not a useEffect) so every badge/pin
  // below - all read the live PALETTE export, see airtagColor.ts - already
  // sees the current palette by the time they render, without threading a
  // `palette` prop through the whole tree just to reach a handful of leaf
  // color lookups.
  if (settings) setColorPalette(settings.color_palette)
  if (settings) setMapTileProvider(settings.map_tile_provider)
  // Same live-module-variable pattern as color_palette above, for CARTO's
  // basemap-tiles API key (mapTiles.ts) - see AppTileLayer/SettingsPlaces.tsx.
  const [cartoApiKey, setCartoApiKeyState] = useState<string | null>(null)
  setCartoApiKey(cartoApiKey)
  // Named geofences (Settings -> Orte) - fetched here (not just inside
  // wherever they're managed) since they label stays on the map/history list
  // app-wide, same reasoning as ownerLocations above.
  const [places, setPlaces] = useState<Place[]>([])
  // Cross-object "Zeitachse" feed (see GET /api/timeline) - fetched
  // independently of the objects/detail selection state below, since it
  // spans every AirTag/device at once rather than following `currentId`.
  const [timeline, setTimeline] = useState<TimelineVisit[]>([])
  // Which single object (if any) the Zeitachse tab is currently narrowed to -
  // drives both TimelinePage's own filtering and, below, which map the
  // Zeitachse tab's map pane shows (its own MapCard/DeviceMapCard instead of
  // OverviewMap). Deliberately separate from `detail` (the Objects tab's own
  // drill-down state) - selecting an object here shouldn't also switch tabs
  // or leave the Objects tab's own selection disturbed once you switch back.
  // currentId/selectedDeviceId are still what's kept in sync (see
  // handleTimelineFilterChange) so the existing per-object report/location
  // fetching just works instead of needing a second copy of it.
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>(null)
  // Zeitachse's range chips (see TimelinePage.tsx) - null means "all
  // available history" (GET /api/timeline's own default), which is also
  // this state's default: capping the feed to a fixed number of points per
  // object (the pre-this-change behavior) could silently cut off well under
  // a day of history for a frequently-polling device, reading as "no more
  // history" when there just was more than the cap allowed. 'today' is
  // fetched as "all" too (see refreshTimeline) and filtered client-side
  // instead, so it respects the viewer's own local calendar day rather than
  // a server-side rolling 24h window in UTC.
  const [timelineRangeDays, setTimelineRangeDays] = useState<TimelineRange>(null)
  // A location picked via a map popup's "Ort hier hinzufügen" (see
  // MapCard.tsx's AddPlaceButton) - consumed by SettingsPanel/SettingsPlaces
  // to jump straight into a new place's editor seeded at that spot, then
  // cleared again so re-opening Orte later doesn't reopen the same seed.
  const [placeSeed, setPlaceSeed] = useState<PlaceSeed | null>(null)
  // Every *enabled* (tracked) owner device - see ObjectsList.tsx, which is
  // the first place a tracked device becomes visible outside Settings.
  const [ownerDevices, setOwnerDevices] = useState<OwnerDevice[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  // Which of the current AirTag's `reports` is shown selected on the map/in
  // the history list - null means "no explicit selection" (map falls back
  // to the latest report). Reset whenever `reports` is reloaded (new AirTag,
  // or fresh poll data) so a stale id never lingers past the data it pointed at.
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null)
  // Same idea as `selectedReportId`, for the selected owner device's location
  // history - keyed by `recorded_at` since owner-device locations have no id
  // in the API response (DeviceHistoryList already used `recorded_at` as its
  // row key). Reset on device switch (handleSelectDevice) - AirTags and
  // owner devices get the same map navigation features, see CLAUDE.md.
  const [selectedDeviceLocationKey, setSelectedDeviceLocationKey] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('objects')
  // Bumped whenever the Einstellungen tab button is clicked while already
  // active, so SettingsPanel's own internal page stack (root/notifications/
  // apple/tracking/places) pops back to root - see handleTabChange and
  // SettingsPanel's resetSignal prop. Objects/Zeitachse don't need this
  // since their own "root" state (detail/timelineFilter) already lives here.
  const [settingsResetSignal, setSettingsResetSignal] = useState(0)
  // Which detail screen (if any) the sheet/map are drilled into - an AirTag's
  // or a tracked device's. Only one of the two `current*Id` values below is
  // ever "the selected one" at a time; this disambiguates which.
  const [detail, setDetail] = useState<'airtag' | 'device' | null>(null)
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

  const refreshOwnerConnected = useCallback(async () => {
    await getOwnerAppleStatus()
      .then((s) => setOwnerConnected(s.connected))
      .catch(() => setOwnerConnected(false))
  }, [])

  const refreshSettings = useCallback(async () => {
    await getSettings()
      .then(setSettings)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshSettings()
  }, [refreshSettings])

  const refreshCartoApiKey = useCallback(async () => {
    await getCartoStatus()
      .then((s) => setCartoApiKeyState(s.api_key))
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshCartoApiKey()
  }, [refreshCartoApiKey])

  // Devices, their live locations, and their histories all come from the
  // same enabled/disabled registry, so they're refreshed together - a
  // device newly enabled (or disabled) in Settings -> Apple-Konten ->
  // Eigene Geräte (OwnerDevicesPanel.tsx, which keeps its own local state)
  // only reaches the Objects list/map through this call, same as a fresh
  // poller fix.
  const refreshOwnerDevices = useCallback(async () => {
    await getOwnerDeviceLocations()
      .then(setOwnerLocations)
      .catch(() => setOwnerLocations([]))
    // Full enabled/disabled registry, not just devices with a recorded fix -
    // without this, a freshly-enabled device with no location yet is
    // invisible everywhere outside Settings (see tasks/todo.md).
    const enabled = await getOwnerDevices()
      .then((ds) => ds.filter((d) => d.enabled))
      .catch(() => [] as OwnerDevice[])
    setOwnerDevices(enabled)
    if (enabled.length === 0) {
      setOwnerLocationHistories({})
      setOwnerLocationStays({})
      return
    }
    const entries = await Promise.all(
      enabled.map((d) =>
        getOwnerDeviceHistory(d.id)
          .then((h) => [d.id, h] as [string, LocationHistory])
          .catch(() => [d.id, { raw: [], stays: [] }] as [string, LocationHistory]),
      ),
    )
    setOwnerLocationHistories(Object.fromEntries(entries.map(([id, h]) => [id, h.raw])))
    setOwnerLocationStays(Object.fromEntries(entries.map(([id, h]) => [id, h.stays])))
  }, [])

  useEffect(() => {
    refreshOwnerConnected()
    refreshOwnerDevices()
  }, [refreshOwnerConnected, refreshOwnerDevices])

  // Guards refreshReports below against a slow response for an airtag the
  // user has since switched away from (or a poll tick that lands mid-
  // switch) landing after a fresher one already resolved.
  const currentIdRef = useRef<string | null>(null)
  useEffect(() => {
    currentIdRef.current = currentId
  }, [currentId])

  // Normally an airtag switch (handleSelect) has no report to pre-select -
  // the effect below resets to null. handleSelectVisit (Zeitachse ->
  // AirtagDetail deep link) needs to land on one specific stay instead, but
  // that selection happens in the same event handler as the currentId
  // change that would otherwise reset it right back to null once this
  // effect re-runs after commit - stash it here so the effect applies it
  // instead of unconditionally clearing it.
  const pendingReportIdRef = useRef<number | null>(null)

  const refreshReports = useCallback(async () => {
    const id = currentId
    if (!id) {
      setReports([])
      setReportStays([])
      return
    }
    const { raw, stays } = await getReports(id)
    if (currentIdRef.current === id) {
      setReports(raw)
      setReportStays(stays)
    }
  }, [currentId])

  useEffect(() => {
    setSelectedReportId(pendingReportIdRef.current)
    pendingReportIdRef.current = null
    refreshReports()
  }, [currentId, refreshReports])

  const refreshPlaces = useCallback(async () => {
    await getPlaces()
      .then(setPlaces)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshPlaces()
  }, [refreshPlaces])

  const refreshTimeline = useCallback(async () => {
    // 'today' is filtered client-side (see TimelinePage.tsx) - fetch
    // everything for it, same as the null/"Alle" case.
    const days = timelineRangeDays === 'today' ? null : timelineRangeDays
    await getTimeline(days)
      .then((t) => setTimeline(t.visits))
      .catch(() => {})
  }, [timelineRangeDays])

  useEffect(() => {
    refreshTimeline()
  }, [refreshTimeline])

  // Re-fetches every endpoint the app depends on, and reports back whether
  // the server was actually reachable - refreshAirtags/refreshReports below
  // let a network failure propagate (no internal .catch), while the other
  // four swallow theirs (they've always tolerated e.g. owner tracking not
  // being connected), so Promise.allSettled is what turns "at least one of
  // these truly failed to reach the server" into a single signal.
  const fullRefresh = useCallback(async () => {
    const results = await Promise.allSettled([
      refreshAirtags(),
      refreshOwnerConnected(),
      refreshOwnerDevices(),
      refreshReports(),
      refreshSettings(),
      refreshPlaces(),
      refreshTimeline(),
    ])
    const reachable = results.every((r) => r.status === 'fulfilled')
    setOffline(!reachable)
    return reachable
  }, [
    refreshAirtags,
    refreshOwnerConnected,
    refreshOwnerDevices,
    refreshReports,
    refreshSettings,
    refreshPlaces,
    refreshTimeline,
  ])

  // Background auto-refresh: re-fetch everything periodically, plus
  // immediately whenever the tab/app regains visibility (switching back
  // from another app, unlocking the screen, ...) so newly-polled locations
  // and settings changes made elsewhere always show up without a manual
  // reload - see AUTO_REFRESH_MS. While the last attempt found the server
  // unreachable, each tick only pings /health instead of re-running every
  // endpoint (no point hammering a server that isn't answering) - the first
  // successful ping triggers one real fullRefresh() to catch back up, and
  // ticks after that go back to normal.
  useEffect(() => {
    async function tick() {
      if (offline) {
        try {
          await ping()
        } catch {
          return
        }
        await fullRefresh()
        return
      }
      await fullRefresh()
    }
    const id = window.setInterval(tick, AUTO_REFRESH_MS)
    function onVisibilityChange() {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [offline, fullRefresh])

  const handleManualRefresh = useCallback(async () => {
    setManualRefreshing(true)
    try {
      await pollNow()
    } catch {
      // A failed poll-now (server unreachable, or a live Apple error
      // tracker.poll_once let through) still falls through to fullRefresh()
      // below, whose own reachability check is what actually surfaces the
      // offline banner.
    } finally {
      await fullRefresh()
      setManualRefreshing(false)
    }
  }, [fullRefresh])

  const currentAirtag = airtags.find((a) => a.id === currentId) ?? null
  const selectedDevice = ownerDevices.find((d) => d.id === selectedDeviceId) ?? null
  const deviceLocationsById: Record<string, OwnerLocation> = Object.fromEntries(
    ownerLocations.map((l) => [l.device_id, l]),
  )
  // Zeitachse's own object filter (see handleTimelineFilterChange) drives
  // this same title/stepper chrome too, alongside the Objects tab's `detail`
  // drill-down - both end up pointing currentId/selectedDeviceId at the same
  // object, so the title/older-newer stepper should reflect whichever one is
  // currently "the thing on screen" instead of only ever the Objects tab's.
  const timelineActiveAirtag = activeTab === 'timeline' && timelineFilter?.type === 'airtag' ? currentAirtag : null
  const timelineActiveDevice = activeTab === 'timeline' && timelineFilter?.type === 'device' ? selectedDevice : null
  const detailName =
    detail === 'airtag'
      ? currentAirtag?.name
      : detail === 'device' && selectedDevice
        ? deviceLabel(selectedDevice)
        : timelineActiveAirtag
          ? timelineActiveAirtag.name
          : timelineActiveDevice
            ? deviceLabel(timelineActiveDevice)
            : null
  const title = detailName ? `AirTagSentry — ${detailName}` : 'AirTagSentry'
  useEffect(() => {
    document.title = title
  }, [title])

  // Older/newer navigation, shared by the mobile title bar's stepper below
  // and the desktop sidebar's HistoryStepper (AirtagDetail.tsx/
  // DeviceDetail.tsx) - moved here from the map popup, see tasks/todo.md.
  // Steps stay-to-stay - reportStays/ownerLocationStays are already computed
  // server-side (see stays.py), so this is a plain array walk, no clustering
  // here anymore. AirTag stays arrive oldest-first, owner-device stays
  // newest-first (see CLAUDE.md), so "older"/"newer" step in opposite index
  // directions for each; mirrored from the same logic MapCard.tsx/
  // DeviceMapCard.tsx use to pick their displayed stay.
  let stepOlder: (() => void) | null = null
  let stepNewer: (() => void) | null = null
  // "Steps back from the latest stay" (1 = latest), counted the same way
  // regardless of which array direction the underlying data arrives in -
  // HistoryStepper just renders whatever count it's given, see the comment
  // there.
  let stepPosition: { current: number; total: number } | null = null
  if ((detail === 'airtag' || timelineActiveAirtag) && currentAirtag) {
    const selectedIndex =
      selectedReportId != null ? reportStays.findIndex((s) => s.anchor_id === selectedReportId) : -1
    const displayedIndex = selectedIndex >= 0 ? selectedIndex : reportStays.length - 1
    const older = displayedIndex > 0 ? reportStays[displayedIndex - 1] : null
    const newer = displayedIndex < reportStays.length - 1 ? reportStays[displayedIndex + 1] : null
    if (older) stepOlder = () => setSelectedReportId(older.anchor_id)
    if (newer) stepNewer = () => setSelectedReportId(newer.anchor_id)
    if (reportStays.length > 0) {
      stepPosition = { current: reportStays.length - displayedIndex, total: reportStays.length }
    }
  } else if ((detail === 'device' || timelineActiveDevice) && selectedDevice) {
    const stays = ownerLocationStays[selectedDevice.id] ?? []
    const selectedIndex =
      selectedDeviceLocationKey != null
        ? stays.findIndex((s) => s.anchor_recorded_at === selectedDeviceLocationKey)
        : -1
    const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
    const older = displayedIndex < stays.length - 1 ? stays[displayedIndex + 1] : null
    const newer = displayedIndex > 0 ? stays[displayedIndex - 1] : null
    if (older) stepOlder = () => setSelectedDeviceLocationKey(older.anchor_recorded_at)
    if (newer) stepNewer = () => setSelectedDeviceLocationKey(newer.anchor_recorded_at)
    if (stays.length > 0) stepPosition = { current: displayedIndex + 1, total: stays.length }
  }

  // Tab bar tap: switching to a different tab lands wherever that tab's own
  // state already is (e.g. back on the AirTag detail you left open) - same
  // as before this change. Tapping the tab that's already active instead
  // acts as a "back to root" (Find My/most iOS tab bars do the same): pop
  // Objects' detail view, clear Zeitachse's object filter, or pop
  // Einstellungen's page stack back to its root list.
  function handleTabChange(tab: TabKey) {
    if (tab !== activeTab) {
      setActiveTab(tab)
      return
    }
    if (tab === 'objects') setDetail(null)
    else if (tab === 'timeline') setTimelineFilter(null)
    else if (tab === 'settings') setSettingsResetSignal((s) => s + 1)
  }

  function handleSelect(id: string) {
    setCurrentId(id)
    setDetail('airtag')
    setActiveTab('objects')
  }

  function handleSelectDevice(id: string) {
    setSelectedDeviceId(id)
    setSelectedDeviceLocationKey(null)
    setDetail('device')
    setActiveTab('objects')
  }

  // ObjectsList's up/down reorder buttons - swaps `id` with its neighbor in
  // the current (enabled-only) device list and persists the whole resulting
  // order (see api.ts's reorderOwnerDevices / db.py's set_owner_devices_order).
  // Optimistic: reorders the local `ownerDevices` state immediately so the
  // swap doesn't visibly wait on the round trip, then reconciles with the
  // server via refreshOwnerDevices (a no-op if the PUT already applied
  // cleanly, a correction if it didn't).
  async function handleReorderDevice(id: string, direction: 'up' | 'down') {
    const index = ownerDevices.findIndex((d) => d.id === id)
    const swapWith = direction === 'up' ? index - 1 : index + 1
    if (index < 0 || swapWith < 0 || swapWith >= ownerDevices.length) return
    const reordered = [...ownerDevices]
    ;[reordered[index], reordered[swapWith]] = [reordered[swapWith], reordered[index]]
    setOwnerDevices(reordered)
    try {
      await reorderOwnerDevices(reordered.map((d) => d.id))
    } finally {
      await refreshOwnerDevices()
    }
  }

  // ObjectsList's up/down reorder buttons for AirTags - mirrors
  // handleReorderDevice/reorderOwnerDevices above (CLAUDE.md's AirTag/owner-
  // device parity rule).
  async function handleReorderAirtag(id: string, direction: 'up' | 'down') {
    const index = airtags.findIndex((a) => a.id === id)
    const swapWith = direction === 'up' ? index - 1 : index + 1
    if (index < 0 || swapWith < 0 || swapWith >= airtags.length) return
    const reordered = [...airtags]
    ;[reordered[index], reordered[swapWith]] = [reordered[swapWith], reordered[index]]
    setAirtags(reordered)
    try {
      await reorderAirtags(reordered.map((a) => a.id))
    } finally {
      await refreshAirtags()
    }
  }

  // "Ort hier hinzufügen" from any map popup (MapCard/DeviceMapCard/
  // OverviewMap) - switches to Settings, where the placeSeed effect below
  // opens Orte straight into a new place's editor at this exact position.
  function handleAddPlace(lat: number, lon: number, name?: string) {
    setPlaceSeed({ lat, lon, name })
    setActiveTab('settings')
  }

  // Picking a history-list entry already re-centers the map on it (see
  // MapCard.tsx/DeviceMapCard.tsx's PanToSelection), but on mobile that pan
  // happened invisibly behind the sheet, which stayed open over the map -
  // minimize it too so the now-centered pin is actually visible (a no-op on
  // desktop, where .sheet[data-state="minimized"] only takes effect under
  // index.css's mobile media query).
  function handleSelectReport(id: number) {
    setSelectedReportId(id)
    setSheetState('minimized')
  }

  function handleSelectDeviceLocation(recordedAt: string) {
    setSelectedDeviceLocationKey(recordedAt)
    setSheetState('minimized')
  }

  // Zeitachse's own object filter (its chip row, or MapCard/DeviceMapCard's
  // onSelectDevice/onMapClick while that tab's map is showing) - narrows the
  // Zeitachse feed to one object and switches its map pane to that object's
  // own MapCard/DeviceMapCard (see the map-pane ternary below). Keeps
  // currentId/selectedDeviceId in sync so the existing per-object report/
  // location-history fetching (refreshReports, refreshOwnerDevices) already
  // covers it - no separate fetch path needed. Resetting selectedReportId/
  // selectedDeviceLocationKey to "no explicit stay selected" here (rather
  // than leaving a stale one from a previous object/tab) mirrors handleSelect/
  // handleSelectDevice's own reset - see pendingReportIdRef's comment for why
  // the AirTag side goes through a ref instead of setting it directly.
  function handleTimelineFilterChange(filter: TimelineFilter) {
    setTimelineFilter(filter)
    if (filter?.type === 'airtag') {
      pendingReportIdRef.current = null
      setCurrentId(filter.id)
    } else if (filter?.type === 'device') {
      setSelectedDeviceId(filter.id)
      setSelectedDeviceLocationKey(null)
    }
  }

  // Zeitachse (TimelinePage) row tap - narrows the feed to that visit's own
  // object (see handleTimelineFilterChange) and additionally pre-selects the
  // specific stay (anchor_id/anchor_recorded_at, see GET /api/timeline) so
  // the map/history land on that exact visit instead of just the object's
  // latest one.
  function handleSelectVisit(visit: TimelineVisit) {
    if (visit.object_type === 'airtag') {
      pendingReportIdRef.current = visit.anchor_id
      setTimelineFilter({ type: 'airtag', id: visit.object_id })
      setCurrentId(visit.object_id)
      if (visit.anchor_id != null) setSelectedReportId(visit.anchor_id)
    } else {
      setTimelineFilter({ type: 'device', id: visit.object_id })
      setSelectedDeviceId(visit.object_id)
      setSelectedDeviceLocationKey(visit.anchor_recorded_at)
    }
    setSheetState('minimized')
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
        {activeTab === 'objects' && detail === 'airtag' && currentAirtag ? (
          <MapCard
            reports={reports}
            airtag={currentAirtag}
            stays={reportStays}
            places={places}
            ownerLocations={ownerLocations}
            ownerLocationHistories={ownerLocationHistories}
            onSelectDevice={handleSelectDevice}
            selectedReportId={selectedReportId}
            onSelectReport={handleSelectReport}
            onMapClick={() => setDetail(null)}
            onAddPlace={handleAddPlace}
          />
        ) : activeTab === 'objects' && detail === 'device' && selectedDevice ? (
          <DeviceMapCard
            device={selectedDevice}
            locations={ownerLocationHistories[selectedDevice.id] ?? []}
            stays={ownerLocationStays[selectedDevice.id] ?? []}
            places={places}
            selectedLocationKey={selectedDeviceLocationKey}
            onSelectLocation={handleSelectDeviceLocation}
            onMapClick={() => setDetail(null)}
            onAddPlace={handleAddPlace}
          />
        ) : /* Zeitachse's own object filter (see handleTimelineFilterChange) -
               same MapCard/DeviceMapCard as the Objects tab's detail view,
               just reached from a chip pick or a row tap instead of drilling
               into AirtagDetail/DeviceDetail. Tapping the map background
               clears the filter back to "Alle" rather than closing a detail
               screen, since there's no detail screen open here. */
        activeTab === 'timeline' && timelineFilter?.type === 'airtag' && currentAirtag ? (
          <MapCard
            reports={reports}
            airtag={currentAirtag}
            stays={reportStays}
            places={places}
            selectedReportId={selectedReportId}
            onSelectReport={handleSelectReport}
            onMapClick={() => setTimelineFilter(null)}
            onAddPlace={handleAddPlace}
          />
        ) : activeTab === 'timeline' && timelineFilter?.type === 'device' && selectedDevice ? (
          <DeviceMapCard
            device={selectedDevice}
            locations={ownerLocationHistories[selectedDevice.id] ?? []}
            stays={ownerLocationStays[selectedDevice.id] ?? []}
            places={places}
            selectedLocationKey={selectedDeviceLocationKey}
            onSelectLocation={handleSelectDeviceLocation}
            onMapClick={() => setTimelineFilter(null)}
            onAddPlace={handleAddPlace}
          />
        ) : (
          <OverviewMap
            airtags={airtags}
            statuses={statuses}
            onSelect={handleSelect}
            ownerLocations={ownerLocations}
            ownerLocationHistories={ownerLocationHistories}
            onSelectDevice={handleSelectDevice}
            onAddPlace={handleAddPlace}
          />
        )}
      </div>

      {/* Offline banner: server unreachable or timed out (see api.ts's
          REQUEST_TIMEOUT_MS and this file's fullRefresh/offline state).
          Shown on both mobile and desktop (unlike the title bar below, which
          is mobile-only) since desktop has no other fixed header to carry
          it. Sits above the title bar (higher z-index) rather than pushing
          it down, so it doesn't shift the map/layout while it's up. */}
      {offline && (
        <div className="pointer-events-none absolute inset-x-0 top-[env(safe-area-inset-top)] z-20 flex justify-center px-3 pt-2">
          <div className="pointer-events-auto rounded-full bg-[var(--destructive)] px-4 py-1.5 text-[13px] font-medium text-white shadow-lg">
            Keine Verbindung zum Server
          </div>
        </div>
      )}

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
          AirTag's or tracked device's name (or "AirTags" with none
          selected/on the overview map) - reusing the same fallback as
          `title` above - plus, while drilled into a detail view with a
          position history, the older/newer stepper (moved here from the
          map popup - see tasks/todo.md) as an absolutely-positioned group
          on the right so the title itself stays centered whether or not
          the stepper is showing. The slot is otherwise still generic so
          future per-item meta (e.g. battery, last-seen) can go here too
          without a layout change. */}
      {/* select-none (+ the iOS-specific touch-callout suppression):
          pointer-events-none above stops taps/clicks from targeting this
          bar, but not WebKit's own text-selection/callout gesture, which
          hit-tests independently of it - without this a press-drag here
          selects the title text instead of passing through to the map. */}
      <div className="pointer-events-none absolute inset-x-0 top-[env(safe-area-inset-top)] z-10 flex h-[var(--header-h)] items-center justify-center border-b border-[var(--divider)] chrome-blur select-none [-webkit-touch-callout:none] md:hidden">
        <span className="truncate px-12 text-[15px] font-semibold text-[var(--text)]">
          {detailName ?? 'AirTags'}
        </span>
        {(stepOlder || stepNewer) && (
          <div className="pointer-events-auto absolute right-2 flex items-center gap-0.5 rounded-full bg-[var(--surface-2)] p-0.5">
            {/* Each button keeps a real `disabled` attribute at the trail's
                start/end (native dimmed style, no focus/activation) - but the
                onClick lives on the wrapping <span>, not the button itself.
                A disabled control is excluded from hit-testing (browsers
                treat it as `pointer-events: none`), so a tap at the
                start/end lands on whatever's directly behind it in paint
                order - normally that's this span (same box, painted just
                behind its own child), which safely no-ops. Without the
                span, that tap fell through the button, the group div, and
                the pointer-events-none title bar behind it, landing on the
                Leaflet map underneath - MapClickHandler read that as "tapped
                away from a pin" and closed the whole detail view back to
                the overview. Sized generously but wide rather than tall
                (extra horizontal padding, modest vertical) since a small
                disabled hit target made stray taps here more likely in the
                first place - it still has to fit inside the fixed
                44px-tall title bar without filling it edge to edge. */}
            <span onClick={() => stepOlder?.()} className="rounded-full">
              <button
                type="button"
                disabled={!stepOlder}
                aria-label="Älterer Standort"
                title="Älterer Standort"
                className="rounded-full px-3.5 py-1.5 text-[var(--text)] disabled:opacity-30"
              >
                <ChevronDownIcon className="h-5 w-5" />
              </button>
            </span>
            <span onClick={() => stepNewer?.()} className="rounded-full">
              <button
                type="button"
                disabled={!stepNewer}
                aria-label="Neuerer Standort"
                title="Neuerer Standort"
                className="rounded-full px-3.5 py-1.5 text-[var(--text)] disabled:opacity-30"
              >
                <ChevronUpIcon className="h-5 w-5" />
              </button>
            </span>
          </div>
        )}
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
          // overflow-clip, not overflow-hidden: this box was only ever meant
          // to visually clip its content to the rounded top corners, never
          // to scroll - but `hidden` still creates a scrollport that's
          // programmatically scrollable (scrollTop) even with no visible
          // scrollbar. AirtagDetail/DeviceDetail's history-row
          // scrollIntoView({ block: 'nearest' }) (fired on every
          // older/newer caret step, including while this sheet sits
          // minimized and its content is merely invisible, not unmounted)
          // walks *every* scrollable ancestor looking for room, and ends up
          // nudging this one by a few px when the nested list's own scroll
          // isn't enough - invisibly clipping the grab handle (this box's
          // first child) out the top since it never scrolls back on its
          // own. `clip` removes the scrollport entirely per the CSS
          // Overflow spec, so it's never a scrollIntoView candidate in the
          // first place - confirmed live: after the escape, this element's
          // own scrollTop read a nonzero value despite no user-facing
          // scrollbar ever having existed for it.
          className="sheet pointer-events-auto flex flex-col overflow-clip rounded-t-2xl bg-[var(--bg)] shadow-[0_-8px_30px_rgba(0,0,0,0.5)] md:h-auto md:flex-1 md:rounded-none md:shadow-none"
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
          {/* invisible (not just relying on the flex-1/min-h-0 shrink) when
              minimized: the grab handle's own rendered height doesn't line
              up pixel-for-pixel with --sheet-handle-h (inline text metrics
              vs. the padding+pill math the CSS comment describes), so
              without this a sliver of whatever's underneath - most visibly
              the detail views' "< AirTags"/"< Objekte" back button - peeked
              out below the handle instead of the map being fully clear. */}
          <div className={`min-h-0 flex-1 ${sheetState === 'minimized' ? 'max-md:invisible' : ''}`}>
            {activeTab === 'timeline' ? (
              <TimelinePage
                visits={timeline}
                airtags={airtags}
                devices={ownerDevices}
                filter={timelineFilter}
                onFilterChange={handleTimelineFilterChange}
                onSelectVisit={handleSelectVisit}
                rangeDays={timelineRangeDays}
                onRangeChange={setTimelineRangeDays}
              />
            ) : activeTab === 'settings' ? (
              <SettingsPanel
                pushStatus={push.status}
                pushBusy={push.busy}
                onEnablePush={push.enable}
                onDisablePush={push.disable}
                onSettingsChanged={setSettings}
                onCartoApiKeyChanged={setCartoApiKeyState}
                places={places}
                onPlacesChanged={refreshPlaces}
                placeSeed={placeSeed}
                onPlaceSeedConsumed={() => setPlaceSeed(null)}
                onRequestExpand={() => setSheetState('expanded')}
                resetSignal={settingsResetSignal}
              />
            ) : detail === 'airtag' && currentAirtag ? (
              <AirtagDetail
                airtag={currentAirtag}
                status={statuses[currentAirtag.id] ?? null}
                stays={reportStays}
                onBack={() => setDetail(null)}
                stepOlder={stepOlder}
                stepNewer={stepNewer}
                stepPosition={stepPosition}
                onChanged={async () => {
                  await refreshAirtags()
                }}
                onDeleted={async () => {
                  await refreshAirtags()
                  setDetail(null)
                }}
                onViewTimeline={() => {
                  handleTimelineFilterChange({ type: 'airtag', id: currentAirtag.id })
                  setActiveTab('timeline')
                }}
              />
            ) : detail === 'device' && selectedDevice ? (
              <DeviceDetail
                device={selectedDevice}
                location={deviceLocationsById[selectedDevice.id] ?? null}
                stays={ownerLocationStays[selectedDevice.id] ?? null}
                onBack={() => setDetail(null)}
                stepOlder={stepOlder}
                stepNewer={stepNewer}
                stepPosition={stepPosition}
                onChanged={refreshOwnerDevices}
                onViewTimeline={() => {
                  handleTimelineFilterChange({ type: 'device', id: selectedDevice.id })
                  setActiveTab('timeline')
                }}
              />
            ) : (
              <ObjectsList
                airtags={airtags}
                statuses={statuses}
                currentId={currentId}
                onSelectAirtag={handleSelect}
                onCreate={handleCreate}
                onReorderAirtag={handleReorderAirtag}
                ownerConnected={ownerConnected}
                devices={ownerDevices}
                deviceLocations={deviceLocationsById}
                selectedDeviceId={selectedDeviceId}
                onSelectDevice={handleSelectDevice}
                onReorderDevice={handleReorderDevice}
                onRefresh={handleManualRefresh}
                refreshing={manualRefreshing}
              />
            )}
          </div>
        </div>
        <TabBar active={activeTab} onChange={handleTabChange} />
      </div>
    </div>
  )
}
