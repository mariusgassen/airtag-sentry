import { useEffect, useState } from 'react'
import { getVapidPublicKey, subscribePush, unsubscribePush } from '../api'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)))
}

export function usePushNotifications() {
  const [status, setStatus] = useState<'idle' | 'active' | 'error'>('idle')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const registration = await navigator.serviceWorker.ready
        const subscription = await registration.pushManager.getSubscription()
        if (subscription) setStatus('active')
      } catch {
        // Unsupported browser or no service worker yet - leave status at 'idle'.
      }
    })()
  }, [])

  async function enable() {
    setBusy(true)
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        alert('Benachrichtigungen wurden nicht erlaubt.')
        return
      }
      const publicKey = await getVapidPublicKey()
      if (!publicKey) {
        alert('Web Push ist serverseitig nicht konfiguriert.')
        return
      }
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
      })
      await subscribePush(subscription)
      setStatus('active')
    } catch (err) {
      console.error(err)
      alert('Aktivierung fehlgeschlagen: ' + (err as Error).message)
      setStatus('error')
    } finally {
      setBusy(false)
    }
  }

  async function disable() {
    setBusy(true)
    try {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      if (subscription) {
        await unsubscribePush(subscription)
        await subscription.unsubscribe()
      }
      setStatus('idle')
    } catch (err) {
      console.error(err)
      alert('Deaktivierung fehlgeschlagen: ' + (err as Error).message)
      setStatus('error')
    } finally {
      setBusy(false)
    }
  }

  return { status, busy, enable, disable }
}
