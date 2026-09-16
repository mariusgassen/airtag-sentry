export interface Airtag {
  id: string
  name: string
  has_key: boolean
  icon: string | null
  color: string | null
}

export interface Report {
  id: number
  timestamp: string
  lat: number
  lon: number
  accuracy: number | null
  confidence: number | null
  // "full" | "medium" | "low" | "very_low" - decoded from FindMy.py's status
  // byte in tracker.py, see format.ts's AIRTAG_BATTERY_LABELS.
  battery_level: string | null
}

export interface ReportStay {
  anchor_id: number
  start: string
  end: string
  count: number
  lat: number
  lon: number
  label: string | null
  place_id: number | null
  battery_level: string | null
}

export interface ReportHistory {
  raw: Report[]
  stays: ReportStay[]
}

export interface Status {
  airtag_id: string
  airtag_name: string
  last_report: { timestamp: string; lat: number; lon: number; battery_level: string | null } | null
  last_alert: { reason: string; timestamp: string } | null
  poll_interval_minutes: number
}

export interface AppSettings {
  polling_interval_minutes: number
  movement_distance_threshold_meters: number
  movement_stillstand_hours: number
  movement_stillstand_movement_meters: number
  movement_alert_on_backfill: boolean
  movement_away_distance_meters: number
  owner_location_max_age_minutes: number
  history_cluster_radius_meters: number
  color_palette: 'vivid' | 'pastel' | 'pastel_white'
  notify_on_distance_threshold: boolean
  notify_on_stillstand_movement: boolean
  notify_on_moved_without_owner: boolean
}

export interface OwnerDevice {
  id: string
  name: string
  device_type: string
  enabled: boolean
  is_primary: boolean
  // User-chosen name/icon/color, mirroring Airtag's - null means "unset":
  // display_name falls back to `name` (the Apple-synced technical name),
  // icon/color fall back to the derived glyph/hash-color. See deviceLabel().
  display_name: string | null
  icon: string | null
  color: string | null
  // Only present on GET /api/owner-devices (not on the rename/enable/primary/
  // appearance mutation responses) - whether this device was present in the
  // background poller's most recent *successful* Apple sync. False means
  // Apple stopped listing it (e.g. removed from iCloud/Find My) - treat a
  // missing value the same as true (unknown yet, not flagged).
  on_account?: boolean
}

export interface OwnerLocation {
  device_id: string
  // Only present on /api/owner-device-locations (a per-device history entry
  // already has its device context from the panel showing it).
  name?: string
  icon?: string | null
  color?: string | null
  recorded_at: string
  lat: number
  lon: number
  horizontal_accuracy: number | null
  // 0.0-1.0 fraction from pyicloud's AppleDevice, or null (e.g. Macs don't
  // report one). battery_status is Apple's raw "Charging"/"NotCharging"/
  // "Unplugged" string - see format.ts's formatDeviceBattery.
  battery_level: number | null
  battery_status: string | null
  // Whether *this* fix's own Apple response actually included a battery
  // reading - false means battery_level/battery_status above were carried
  // forward from a previous fix (or, with none yet, are just null) by
  // db.py's record_owner_device_location. Lets the history list show which
  // readings are real vs. inherited, for later visualization (a
  // battery-over-time chart shouldn't treat a filled gap as a real sample).
  battery_reported: boolean
}

export interface LocationStay {
  anchor_recorded_at: string
  start: string
  end: string
  count: number
  lat: number
  lon: number
  label: string | null
  place_id: number | null
  battery_level: number | null
  battery_status: string | null
  battery_reported: boolean
}

export interface LocationHistory {
  raw: OwnerLocation[]
  stays: LocationStay[]
}

export interface AppleTwoFactorMethod {
  index: number
  kind: 'trusted_device' | 'sms' | 'unknown'
  phone_number: string | null
}

export interface AppleLoginResult {
  requires_2fa: boolean
  methods: AppleTwoFactorMethod[]
}

export class ApiError extends Error {}

// A hung request (server unreachable, or a response that never arrives) would
// otherwise leave a caller awaiting forever - App.tsx's offline detection
// needs every call to eventually settle so it can distinguish "the server
// said no" (a normal ApiError) from "the server isn't answering at all".
const REQUEST_TIMEOUT_MS = 10_000

// poll-now (below) runs a live, synchronous Apple poll server-side (all
// AirTags plus every enabled owner device) instead of a plain DB read, so it
// routinely takes longer than REQUEST_TIMEOUT_MS under perfectly normal
// conditions. Using the default timeout for it used to abort the request
// client-side while the server was still busy with that same poll, and
// App.tsx's handleManualRefresh immediately followed up with a fullRefresh()
// that then raced the still-running poll and occasionally timed out too -
// surfacing the offline banner on a manual refresh even though the server
// was reachable the whole time, something the passive background tick never
// triggers since it never calls poll-now.
const POLL_NOW_TIMEOUT_MS = 60_000

async function apiFetch(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timeout)
  }
  if (res.status === 401) {
    window.location.href = '/login'
    // Never resolves - the redirect above takes over the page.
    return new Promise<Response>(() => {})
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body.detail || `HTTP ${res.status}`)
  }
  return res
}

/** Cheap reachability probe against the public, DB-backed /health route (see
 * web/app.py) - used by App.tsx's offline banner to detect the server coming
 * back without re-fetching every AirTag/device/settings endpoint on every
 * check while it's still down. */
export async function ping(): Promise<void> {
  await apiFetch('/health')
}

/** Triggers an immediate full poll (AirTags + owner devices), independent of
 * the scheduled background interval - see tracker.poll_once via
 * POST /api/poll-now. Callers should re-fetch the usual data endpoints
 * afterwards to pick up whatever this just wrote. */
export async function pollNow(): Promise<void> {
  await apiFetch('/api/poll-now', { method: 'POST' }, POLL_NOW_TIMEOUT_MS)
}

export async function getAirtags(): Promise<Airtag[]> {
  return (await apiFetch('/api/airtags')).json()
}

export async function createAirtag(name: string): Promise<Airtag> {
  return (await apiFetch('/api/airtags', { method: 'POST', body: JSON.stringify({ name }) })).json()
}

export async function renameAirtag(id: string, name: string): Promise<{ id: string; name: string }> {
  return (
    await apiFetch(`/api/airtags/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
  ).json()
}

export async function deleteAirtag(id: string): Promise<void> {
  await apiFetch(`/api/airtags/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function setAirtagAppearance(
  id: string,
  icon: string | null,
  color: string | null,
): Promise<{ id: string; icon: string | null; color: string | null }> {
  return (
    await apiFetch(`/api/airtags/${encodeURIComponent(id)}/appearance`, {
      method: 'PATCH',
      body: JSON.stringify({ icon, color }),
    })
  ).json()
}

export async function setAirtagKeyB64(id: string, privateKeyB64: string): Promise<void> {
  await apiFetch(`/api/airtags/${encodeURIComponent(id)}/key`, {
    method: 'POST',
    body: JSON.stringify({ private_key_b64: privateKeyB64 }),
  })
}

export async function setAirtagKeyJson(id: string, accessoryJson: unknown): Promise<void> {
  await apiFetch(`/api/airtags/${encodeURIComponent(id)}/key`, {
    method: 'POST',
    body: JSON.stringify({ accessory_json: accessoryJson }),
  })
}

export async function deleteAirtagKey(id: string): Promise<void> {
  await apiFetch(`/api/airtags/${encodeURIComponent(id)}/key`, { method: 'DELETE' })
}

export async function getReports(airtagId: string, limit = 500): Promise<ReportHistory> {
  return (
    await apiFetch(`/api/reports?airtag_id=${encodeURIComponent(airtagId)}&limit=${limit}`)
  ).json()
}

export async function getStatus(airtagId: string): Promise<Status> {
  return (await apiFetch(`/api/status?airtag_id=${encodeURIComponent(airtagId)}`)).json()
}

export async function getAddress(lat: number, lon: number): Promise<string | null> {
  const res = await apiFetch(`/api/geocode?lat=${lat}&lon=${lon}`)
  const data: { address: string | null } = await res.json()
  return data.address
}

export interface AddressSearchResult {
  display_name: string
  lat: number
  lon: number
}

export async function searchAddress(query: string): Promise<AddressSearchResult[]> {
  return (await apiFetch(`/api/geocode/search?q=${encodeURIComponent(query)}`)).json()
}

export async function getSettings(): Promise<AppSettings> {
  return (await apiFetch('/api/settings')).json()
}

export async function updateSettings(settings: AppSettings): Promise<AppSettings> {
  return (
    await apiFetch('/api/settings', { method: 'PUT', body: JSON.stringify(settings) })
  ).json()
}

export async function getOwnerDevices(): Promise<OwnerDevice[]> {
  return (await apiFetch('/api/owner-devices')).json()
}

export async function setOwnerDeviceEnabled(id: string, enabled: boolean): Promise<OwnerDevice> {
  // device_id travels in the body, not the URL path - Apple's device ids can
  // contain a literal "/" (they're opaque base64-ish blobs), which breaks
  // path-based routing even when percent-encoded, since ASGI/proxy layers
  // decode "%2F" back into a delimiter before routing ever sees it.
  return (
    await apiFetch('/api/owner-devices', {
      method: 'PUT',
      body: JSON.stringify({ device_id: id, enabled }),
    })
  ).json()
}

export async function setOwnerDevicePrimary(id: string): Promise<OwnerDevice> {
  return (
    await apiFetch('/api/owner-devices/primary', {
      method: 'PUT',
      body: JSON.stringify({ device_id: id }),
    })
  ).json()
}

export async function clearOwnerDevicePrimary(): Promise<void> {
  await apiFetch('/api/owner-devices/primary', { method: 'DELETE' })
}

export async function renameOwnerDevice(id: string, displayName: string | null): Promise<OwnerDevice> {
  return (
    await apiFetch('/api/owner-devices/rename', {
      method: 'PATCH',
      body: JSON.stringify({ device_id: id, display_name: displayName }),
    })
  ).json()
}

export async function setOwnerDeviceAppearance(
  id: string,
  icon: string | null,
  color: string | null,
): Promise<OwnerDevice> {
  return (
    await apiFetch('/api/owner-devices/appearance', {
      method: 'PATCH',
      body: JSON.stringify({ device_id: id, icon, color }),
    })
  ).json()
}

export async function getOwnerDeviceLocations(): Promise<OwnerLocation[]> {
  return (await apiFetch('/api/owner-device-locations')).json()
}

export async function getOwnerDeviceHistory(id: string, limit = 200): Promise<LocationHistory> {
  return (
    await apiFetch(
      `/api/owner-devices/history?device_id=${encodeURIComponent(id)}&limit=${limit}`,
    )
  ).json()
}

export async function playOwnerDeviceSound(id: string): Promise<void> {
  await apiFetch('/api/owner-devices/play-sound', {
    method: 'POST',
    body: JSON.stringify({ device_id: id }),
  })
}

export async function getAppleStatus(): Promise<{ connected: boolean }> {
  return (await apiFetch('/api/apple/status')).json()
}

export async function appleLogin(email: string, password: string): Promise<AppleLoginResult> {
  return (
    await apiFetch('/api/apple/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  ).json()
}

export async function appleSelectTwoFactorMethod(methodIndex: number): Promise<void> {
  await apiFetch('/api/apple/2fa/select', {
    method: 'POST',
    body: JSON.stringify({ method_index: methodIndex }),
  })
}

export async function appleSubmitTwoFactorCode(code: string): Promise<void> {
  await apiFetch('/api/apple/2fa/submit', { method: 'POST', body: JSON.stringify({ code }) })
}

export async function appleImportSession(sessionJson: unknown): Promise<void> {
  await apiFetch('/api/apple/session', {
    method: 'POST',
    body: JSON.stringify({ session_json: sessionJson }),
  })
}

export async function appleDisconnect(): Promise<void> {
  await apiFetch('/api/apple', { method: 'DELETE' })
}

export async function getOwnerAppleStatus(): Promise<{
  connected: boolean
  primary_device_id: string | null
  primary_device_name: string | null
  // The most recent background poll's live Apple call failure (a lapsed
  // session, a transient network error, ...), if any - cleared again on the
  // next successful sync.
  last_sync_error: string | null
  // Current Family Sharing filter, settable via ownerAppleSetIncludeFamily
  // without a re-login - see owner_tracking.set_include_family.
  include_family_devices: boolean
}> {
  return (await apiFetch('/api/apple/owner/status')).json()
}

export async function ownerAppleLogin(
  appleId: string,
  password: string,
  includeFamily = false,
): Promise<AppleLoginResult> {
  return (
    await apiFetch('/api/apple/owner/login', {
      method: 'POST',
      body: JSON.stringify({ apple_id: appleId, password, include_family: includeFamily }),
    })
  ).json()
}

export async function ownerAppleSubmitTwoFactorCode(code: string): Promise<void> {
  await apiFetch('/api/apple/owner/2fa/submit', { method: 'POST', body: JSON.stringify({ code }) })
}

export async function ownerAppleDisconnect(): Promise<void> {
  await apiFetch('/api/apple/owner', { method: 'DELETE' })
}

export async function ownerAppleSetIncludeFamily(includeFamily: boolean): Promise<void> {
  await apiFetch('/api/apple/owner/family', {
    method: 'PATCH',
    body: JSON.stringify({ include_family: includeFamily }),
  })
}

export interface TelegramStatus {
  connected: boolean
  chat_id: string | null
  bot_commands_enabled: boolean
}

export async function getTelegramStatus(): Promise<TelegramStatus> {
  return (await apiFetch('/api/notifications/telegram')).json()
}

export async function setTelegramCredentials(botToken: string, chatId: string): Promise<TelegramStatus> {
  return (
    await apiFetch('/api/notifications/telegram', {
      method: 'POST',
      body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
    })
  ).json()
}

export async function deleteTelegramCredentials(): Promise<void> {
  await apiFetch('/api/notifications/telegram', { method: 'DELETE' })
}

export async function enableTelegramCommands(): Promise<void> {
  await apiFetch('/api/notifications/telegram/commands', { method: 'POST' })
}

export async function disableTelegramCommands(): Promise<void> {
  await apiFetch('/api/notifications/telegram/commands', { method: 'DELETE' })
}

export interface MqttStatus {
  connected: boolean
  host: string | null
  port: number | null
  username: string | null
  use_tls: boolean
}

export async function getMqttStatus(): Promise<MqttStatus> {
  return (await apiFetch('/api/notifications/mqtt')).json()
}

export async function setMqttSettings(
  host: string,
  port: number,
  username: string,
  password: string,
  useTls: boolean,
): Promise<MqttStatus> {
  return (
    await apiFetch('/api/notifications/mqtt', {
      method: 'POST',
      body: JSON.stringify({
        host,
        port,
        username: username || null,
        password: password || null,
        use_tls: useTls,
      }),
    })
  ).json()
}

export async function deleteMqttSettings(): Promise<void> {
  await apiFetch('/api/notifications/mqtt', { method: 'DELETE' })
}

export interface NotificationTestResult {
  channel: string
  ok: boolean
  error?: string
}

export async function testNotifications(): Promise<{ results: NotificationTestResult[] }> {
  return (await apiFetch('/api/notifications/test', { method: 'POST' })).json()
}

export interface HaTokenStatus {
  configured: boolean
  created_at: string | null
}

export async function getHaTokenStatus(): Promise<HaTokenStatus> {
  return (await apiFetch('/api/ha/token/status')).json()
}

export async function generateHaToken(): Promise<{ token: string }> {
  return (await apiFetch('/api/ha/token', { method: 'POST' })).json()
}

export async function revokeHaToken(): Promise<void> {
  await apiFetch('/api/ha/token', { method: 'DELETE' })
}

export async function getVapidPublicKey(): Promise<string | null> {
  const res = await fetch('/api/push/vapid-public-key')
  if (!res.ok) return null
  return (await res.json()).publicKey
}

export async function subscribePush(subscription: PushSubscription): Promise<void> {
  await apiFetch('/api/push/subscribe', { method: 'POST', body: JSON.stringify(subscription.toJSON()) })
}

export async function unsubscribePush(subscription: PushSubscription): Promise<void> {
  await apiFetch('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: subscription.endpoint }) })
}

export interface Place {
  id: number
  name: string
  lat: number
  lon: number
  radius_meters: number
}

export async function getPlaces(): Promise<Place[]> {
  return (await apiFetch('/api/places')).json()
}

export async function createPlace(input: {
  name: string
  lat: number
  lon: number
  radius_meters: number
}): Promise<Place> {
  return (await apiFetch('/api/places', { method: 'POST', body: JSON.stringify(input) })).json()
}

export async function updatePlace(
  id: number,
  input: { name: string; lat: number; lon: number; radius_meters: number },
): Promise<Place> {
  return (
    await apiFetch(`/api/places/${id}`, { method: 'PUT', body: JSON.stringify(input) })
  ).json()
}

export async function deletePlace(id: number): Promise<void> {
  await apiFetch(`/api/places/${id}`, { method: 'DELETE' })
}

export async function setGeocodeCorrection(
  lat: number,
  lon: number,
  correctedName: string,
): Promise<void> {
  await apiFetch('/api/geocode/correction', {
    method: 'PUT',
    body: JSON.stringify({ lat, lon, corrected_name: correctedName }),
  })
}

export async function clearGeocodeCorrection(lat: number, lon: number): Promise<void> {
  await apiFetch(`/api/geocode/correction?lat=${lat}&lon=${lon}`, { method: 'DELETE' })
}
