import { createElementObject, createLayerComponent, extendContext } from '@react-leaflet/core'
import type { PropsWithChildren } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import { clusterPinIcon } from '../mapIcons'

type Props = PropsWithChildren<L.MarkerClusterGroupOptions>

/**
 * Groups nearby child `<Marker>` pins into a single cluster badge that splits
 * apart on zoom/click (leaflet.markercluster) - keeps OverviewMap.tsx's
 * all-AirTags-and-devices view readable as more objects get tracked, instead
 * of every pin fully overlapping once several sit close together. A thin
 * `@react-leaflet/core` wrapper (same pattern react-leaflet's own LayerGroup
 * uses internally) rather than a community React cluster package, since none
 * of those yet support react-leaflet v5/React 19 - this keeps ordinary
 * `<Marker>`/`<Popup>` JSX working unchanged as children.
 *
 * Cluster badges default to `clusterPinIcon` (matches the app's own pin
 * styling, see mapIcons.ts) instead of leaflet.markercluster's stock grey/
 * yellow/orange circles - `MarkerCluster.Default.css`, which only supplies
 * those, is deliberately not imported. Callers can still override via
 * `iconCreateFunction`.
 */
export const MarkerClusterGroup = createLayerComponent<L.MarkerClusterGroup, Props>(
  ({ children: _children, ...options }, context) => {
    const group = L.markerClusterGroup({
      iconCreateFunction: (cluster) => clusterPinIcon(cluster.getChildCount()),
      ...options,
    })
    return createElementObject(group, extendContext(context, { layerContainer: group }))
  },
)
