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
}

export interface Status {
  airtag_id: string
  airtag_name: string
  last_report: { timestamp: string; lat: number; lon: number } | null
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

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
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

export async function getReports(airtagId: string, limit = 500): Promise<Report[]> {
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

export async function getOwnerDeviceHistory(id: string, limit = 200): Promise<OwnerLocation[]> {
  return (
    await apiFetch(
      `/api/owner-devices/history?device_id=${encodeURIComponent(id)}&limit=${limit}`,
    )
  ).json()
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
