export interface Airtag {
  id: string
  name: string
  has_key: boolean
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

export interface OwnerLocation {
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

export async function getSettings(): Promise<AppSettings> {
  return (await apiFetch('/api/settings')).json()
}

export async function updateSettings(settings: AppSettings): Promise<AppSettings> {
  return (
    await apiFetch('/api/settings', { method: 'PUT', body: JSON.stringify(settings) })
  ).json()
}

export async function getOwnerLocation(): Promise<OwnerLocation | null> {
  return (await apiFetch('/api/owner-location')).json()
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

export async function appleDisconnect(): Promise<void> {
  await apiFetch('/api/apple', { method: 'DELETE' })
}

export async function getOwnerAppleStatus(): Promise<{ connected: boolean }> {
  return (await apiFetch('/api/apple/owner/status')).json()
}

export async function ownerAppleLogin(appleId: string, password: string): Promise<AppleLoginResult> {
  return (
    await apiFetch('/api/apple/owner/login', {
      method: 'POST',
      body: JSON.stringify({ apple_id: appleId, password }),
    })
  ).json()
}

export async function ownerAppleSubmitTwoFactorCode(code: string): Promise<void> {
  await apiFetch('/api/apple/owner/2fa/submit', { method: 'POST', body: JSON.stringify({ code }) })
}

export async function ownerAppleDisconnect(): Promise<void> {
  await apiFetch('/api/apple/owner', { method: 'DELETE' })
}

export async function getVapidPublicKey(): Promise<string | null> {
  const res = await fetch('/api/push/vapid-public-key')
  if (!res.ok) return null
  return (await res.json()).publicKey
}

export async function subscribePush(subscription: PushSubscription): Promise<void> {
  await apiFetch('/api/push/subscribe', { method: 'POST', body: JSON.stringify(subscription.toJSON()) })
}
