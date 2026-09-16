import { useEffect, useRef } from 'react'
import L from 'leaflet'
// Side-effect import augments L.Circle/L.Path.prototype with `.pm` at
// runtime, and (as of the installed 2.20.x) also ships its own `declare
// module 'leaflet'` merging `pm: PM.PMLayer` onto `L.Path` in
// @geoman-io/leaflet-geoman-free/dist/leaflet-geoman.d.ts - so no manual
// cast is needed to call `circle.pm.enable(...)` below; TypeScript already
// knows about it. The CSS import (not mentioned in the original plan for
// this component) styles the drag/resize handle markers - without it they
// render as bare unstyled dots with no "move" cursor, which made dragging
// hard to discover in manual testing.
import '@geoman-io/leaflet-geoman-free'
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css'
import { useMap } from 'react-leaflet'
import { PLACE_CIRCLE_COLOR } from '../mapIcons'

/**
 * An imperative Leaflet Circle (not a declarative react-leaflet `<Circle>`)
 * with leaflet-geoman's drag-to-move-center / drag-to-resize-radius editing
 * enabled - there's no react-leaflet prop API for geoman's editing, so this
 * mounts a real L.Circle once and only ever reads/writes it imperatively.
 * `center`/`radius` props seed the *initial* geometry only; after that the
 * circle itself is the source of truth, mirrored back to the caller via
 * `onChange` whenever geoman fires an edit event - see
 * https://geoman.io/docs/leaflet/modes/edit-mode for the exact event names
 * (`pm:edit` during a drag, `pm:markerdragend` when a handle drag finishes).
 */
export function EditableCircle({
  center,
  radius,
  onChange,
}: {
  center: [number, number]
  radius: number
  onChange: (center: [number, number], radius: number) => void
}) {
  const map = useMap()
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    const circle = L.circle(center, {
      radius,
      color: PLACE_CIRCLE_COLOR,
      fillColor: PLACE_CIRCLE_COLOR,
      fillOpacity: 0.15,
      weight: 2,
    }).addTo(map)

    function sync() {
      const latlng = circle.getLatLng()
      onChangeRef.current([latlng.lat, latlng.lng], circle.getRadius())
    }
    circle.on('pm:edit', sync)
    circle.on('pm:markerdragend', sync)
    circle.pm.enable({ draggable: true })

    return () => {
      circle.off('pm:edit', sync)
      circle.off('pm:markerdragend', sync)
      circle.remove()
    }
    // Mount once - the circle layer is the source of truth after that;
    // re-running this for every `center`/`radius` prop change (e.g. from the
    // very `onChange` calls this effect fires) would fight the user's
    // in-progress drag by recreating the layer under their cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  return null
}
