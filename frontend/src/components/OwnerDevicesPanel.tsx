import { useEffect, useState } from 'react'
import type { OwnerDevice } from '../api'
import {
  clearOwnerDevicePrimary,
  getOwnerAppleStatus,
  getOwnerDevices,
  setOwnerDeviceEnabled,
  setOwnerDevicePrimary,
} from '../api'
import { Row, Section, Switch } from './AirtagDetail'
import { StarIcon } from './icons'

/** Lists the owner's Apple devices (Macs, iPhones, iPads, Watches - see
 * owner_tracking.py) once the "Eigener Standort" Apple session is connected,
 * with a toggle to opt each one into tracking. Exactly one device can
 * additionally be marked *primary* (the star) - that's the one used for
 * "moved without you" away-correlation and the map's location trail; every
 * other tracked device is still tracked, it just doesn't affect either.
 * This panel only manages *which* devices are tracked - a tracked device's
 * location and history show up in the main Objekte list once selected
 * there (ObjectsList.tsx / DeviceDetail.tsx), not here. AirPods don't show
 * up here - they're tracked the same way an AirTag is, via the Manage
 * AirTags key-upload flow. */
export function OwnerDevicesPanel() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [devices, setDevices] = useState<OwnerDevice[] | null>(null)
  const [devicesError, setDevicesError] = useState<string | null>(null)

  useEffect(() => {
    getOwnerAppleStatus().then((s) => setConnected(s.connected))
  }, [])

  useEffect(() => {
    if (!connected) return
    getOwnerDevices()
      .then((d) => {
        setDevicesError(null)
        setDevices(d)
      })
      .catch((err) => setDevicesError((err as Error).message))
  }, [connected])

  async function loadDevices() {
    setDevicesError(null)
    try {
      setDevices(await getOwnerDevices())
    } catch (err) {
      setDevicesError((err as Error).message)
    }
  }

  async function toggle(device: OwnerDevice) {
    try {
      const updated = await setOwnerDeviceEnabled(device.id, !device.enabled)
      setDevices((ds) => ds?.map((d) => (d.id === updated.id ? updated : d)) ?? ds)
    } catch (err) {
      alert('Ändern fehlgeschlagen: ' + (err as Error).message)
    }
  }

  async function togglePrimary(device: OwnerDevice) {
    try {
      if (device.is_primary) {
        await clearOwnerDevicePrimary()
        setDevices((ds) => ds?.map((d) => ({ ...d, is_primary: false })) ?? ds)
        return
      }
      const updated = await setOwnerDevicePrimary(device.id)
      // Picking a new primary is exclusive and force-enables the device server-side.
      setDevices((ds) => ds?.map((d) => (d.id === updated.id ? updated : { ...d, is_primary: false })) ?? ds)
    } catch (err) {
      alert('Ändern fehlgeschlagen: ' + (err as Error).message)
    }
  }

  if (!connected) return null

  return (
    <div className="px-3">
      <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
        Eigene Geräte
      </p>
      <Section>
        {devicesError ? (
          <div className="px-4 py-3">
            <p className="text-[0.78rem] text-[var(--destructive)]">{devicesError}</p>
            <button
              type="button"
              onClick={loadDevices}
              className="mt-2 rounded-lg border border-[var(--divider)] px-3 py-1.5 text-sm"
            >
              Erneut versuchen
            </button>
          </div>
        ) : devices === null ? (
          <p className="px-4 py-3 text-sm text-[var(--text-secondary)]">Lädt…</p>
        ) : devices.length === 0 ? (
          <p className="px-4 py-3 text-sm text-[var(--text-secondary)]">Keine Geräte gefunden.</p>
        ) : (
          devices.map((d) => (
            <Row
              key={d.id}
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
                  <Switch checked={d.enabled} onChange={() => toggle(d)} />
                </div>
              }
            />
          ))
        )}
      </Section>
    </div>
  )
}
