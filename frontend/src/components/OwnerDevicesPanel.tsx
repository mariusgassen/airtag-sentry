import { useEffect, useState } from 'react'
import type { OwnerDevice, OwnerLocation } from '../api'
import {
  clearOwnerDevicePrimary,
  getOwnerAppleStatus,
  getOwnerDeviceHistory,
  getOwnerDevices,
  setOwnerDeviceEnabled,
  setOwnerDevicePrimary,
} from '../api'
import { Row, Section } from './AirtagDetail'
import { ChevronRightIcon, StarIcon } from './icons'

/** Lists the owner's Apple devices (Macs, iPhones, iPads, Watches - see
 * owner_tracking.py) once the "Eigener Standort" Apple session is connected,
 * with a toggle to opt each one into tracking and an expandable history for
 * enabled ones. Exactly one device can additionally be marked *primary* (the
 * star) - that's the one used for "moved without you" away-correlation and
 * the map's location trail; every other tracked device is still listed with
 * its own history, it just doesn't affect either. AirPods don't show up
 * here - they're tracked the same way an AirTag is, via the Manage AirTags
 * key-upload flow. */
export function OwnerDevicesPanel() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [devices, setDevices] = useState<OwnerDevice[] | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<string, OwnerLocation[] | null>>({})

  useEffect(() => {
    getOwnerAppleStatus().then((s) => setConnected(s.connected))
  }, [])

  useEffect(() => {
    if (connected) {
      getOwnerDevices().then(setDevices)
    }
  }, [connected])

  async function toggle(device: OwnerDevice) {
    const updated = await setOwnerDeviceEnabled(device.id, !device.enabled)
    setDevices((ds) => ds?.map((d) => (d.id === updated.id ? updated : d)) ?? ds)
  }

  async function togglePrimary(device: OwnerDevice) {
    if (device.is_primary) {
      await clearOwnerDevicePrimary()
      setDevices((ds) => ds?.map((d) => ({ ...d, is_primary: false })) ?? ds)
      return
    }
    const updated = await setOwnerDevicePrimary(device.id)
    // Picking a new primary is exclusive and force-enables the device server-side.
    setDevices((ds) => ds?.map((d) => (d.id === updated.id ? updated : { ...d, is_primary: false })) ?? ds)
  }

  async function toggleHistory(id: string) {
    const next = openId === id ? null : id
    setOpenId(next)
    if (next && !(next in history)) {
      setHistory((h) => ({ ...h, [next]: null }))
      const rows = await getOwnerDeviceHistory(next)
      setHistory((h) => ({ ...h, [next]: rows }))
    }
  }

  if (!connected) return null

  return (
    <div className="px-3">
      <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
        Eigene Geräte
      </p>
      <Section>
        {devices === null ? (
          <p className="px-4 py-3 text-sm text-[var(--text-secondary)]">Lädt…</p>
        ) : devices.length === 0 ? (
          <p className="px-4 py-3 text-sm text-[var(--text-secondary)]">Keine Geräte gefunden.</p>
        ) : (
          devices.map((d, i) => (
            <div key={d.id} className={i > 0 ? 'border-t border-[var(--divider)]' : ''}>
              <Row
                label={d.name}
                trailing={
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => togglePrimary(d)}
                      title={d.is_primary ? 'Nicht mehr als eigenen Standort verwenden' : 'Als eigenen Standort verwenden'}
                      aria-label={d.is_primary ? 'Nicht mehr als eigenen Standort verwenden' : 'Als eigenen Standort verwenden'}
                      className={`flex h-8 w-8 items-center justify-center rounded-full ${d.is_primary ? 'text-[var(--accent)]' : 'text-[var(--text-secondary)]'}`}
                    >
                      <StarIcon className="h-4 w-4" filled={d.is_primary} />
                    </button>
                    <input
                      type="checkbox"
                      checked={d.enabled}
                      onChange={() => toggle(d)}
                      className="h-5 w-5 accent-[var(--accent)]"
                    />
                  </div>
                }
                bordered={false}
              />
              {d.enabled && (
                <>
                  <Row
                    label="Verlauf"
                    trailing={
                      <ChevronRightIcon
                        className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${openId === d.id ? 'rotate-90' : ''}`}
                      />
                    }
                    onClick={() => toggleHistory(d.id)}
                  />
                  {openId === d.id && <OwnerLocationHistoryList entries={history[d.id] ?? null} />}
                </>
              )}
            </div>
          ))
        )}
      </Section>
    </div>
  )
}

function OwnerLocationHistoryList({ entries }: { entries: OwnerLocation[] | null }) {
  if (entries === null) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Lädt…
      </div>
    )
  }
  if (entries.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch kein Standortverlauf vorhanden.
      </div>
    )
  }
  return (
    <div className="max-h-64 overflow-y-auto border-t border-[var(--divider)]">
      {entries.map((loc, i) => (
        <div
          key={loc.recorded_at}
          className={`flex items-center justify-between px-4 py-2 text-sm ${i > 0 ? 'border-t border-[var(--divider)]' : ''}`}
        >
          <span>{new Date(loc.recorded_at).toLocaleString()}</span>
          <span className="text-[var(--text-secondary)]">
            {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  )
}
