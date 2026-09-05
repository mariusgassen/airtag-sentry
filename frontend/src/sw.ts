/// <reference lib="webworker" />
import { precacheAndRoute } from 'workbox-precaching'
import type { PrecacheEntry } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<PrecacheEntry | string>
}

// Workbox's build-time precache manifest (app shell assets) gets injected here.
precacheAndRoute(self.__WB_MANIFEST)

interface PushPayload {
  title: string
  message: string
}

self.addEventListener('push', (event: PushEvent) => {
  let payload: PushPayload = { title: 'AirTagSentry', message: 'Neue Aktivität.' }
  if (event.data) {
    try {
      payload = event.data.json()
    } catch {
      payload = { ...payload, message: event.data.text() }
    }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.message,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
    }),
  )
})

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) return (client as WindowClient).focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow('/')
    }),
  )
})
