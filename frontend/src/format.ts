export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'gerade eben'
  if (minutes < 60) return `vor ${minutes} Minute${minutes === 1 ? '' : 'n'}`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `vor ${hours} Stunde${hours === 1 ? '' : 'n'}`
  const days = Math.round(hours / 24)
  if (days < 7) return `vor ${days} Tag${days === 1 ? '' : 'en'}`
  return new Date(iso).toLocaleDateString()
}

/** formatRelative()'s output reads correctly lowercase mid-sentence (e.g.
 * "Zuletzt gesehen vor 5 Minuten"); capitalize it when shown standalone. */
export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Human-readable labels for Alert.reason values from the backend
 * (airtag_sentry/movement.py / tracker.py). */
export const ALERT_REASON_LABELS: Record<string, string> = {
  distance_threshold: 'Bewegung',
  stillstand_movement: 'Bewegung nach Stillstand',
  moved_without_owner: 'Bewegung ohne dich',
}

export function formatAlertReason(reason: string): string {
  return ALERT_REASON_LABELS[reason] ?? reason
}

/** The name to show for an owner device: its user-chosen display_name, or -
 * if unset - the Apple-synced technical name (see rename_owner_device). */
export function deviceLabel(device: { name: string; display_name: string | null }): string {
  return device.display_name ?? device.name
}

/** Human-readable labels for Report.battery_level values from the backend
 * (FindMy.py's status byte, decoded in tracker.py). */
export const AIRTAG_BATTERY_LABELS: Record<string, string> = {
  full: 'Voll',
  medium: 'Mittel',
  low: 'Niedrig',
  very_low: 'Sehr niedrig',
}

export function formatAirtagBattery(level: string): string {
  return AIRTAG_BATTERY_LABELS[level] ?? level
}

/** Whether a battery reading is low enough to call out visually - AirTags'
 * qualitative "low"/"very_low" levels, or an owner device below 20%. */
export function isLowBattery(level: string | number): boolean {
  return typeof level === 'number' ? level < 0.2 : level === 'low' || level === 'very_low'
}

/** OwnerLocation.battery_level is a 0.0-1.0 fraction (pyicloud); battery_status
 * is Apple's raw charging-state string, appended when it's actually charging. */
export function formatDeviceBattery(level: number, status: string | null): string {
  const percent = `${Math.round(level * 100)} %`
  return status === 'Charging' ? `${percent} (lädt)` : percent
}
