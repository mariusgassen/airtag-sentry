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

export async function getVapidPublicKey(): Promise<string | null> {
  const res = await fetch('/api/push/vapid-public-key')
  if (!res.ok) return null
  return (await res.json()).publicKey
}

export async function subscribePush(subscription: PushSubscription): Promise<void> {
  await apiFetch('/api/push/subscribe', { method: 'POST', body: JSON.stringify(subscription.toJSON()) })
}
