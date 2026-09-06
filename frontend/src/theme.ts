import { useEffect, useState } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'airtagsentry.theme'

export function getStoredTheme(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

function effectiveScheme(pref: ThemePreference): 'light' | 'dark' {
  if (pref === 'light' || pref === 'dark') return pref
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(pref: ThemePreference) {
  const root = document.documentElement
  if (pref === 'system') delete root.dataset.theme
  else root.dataset.theme = pref

  // Keep the browser/PWA chrome (address bar, status bar background) in
  // sync so it never mismatches the app's own background.
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', effectiveScheme(pref) === 'dark' ? '#000000' : '#f2f2f7')

  // apple-mobile-web-app-status-bar-style can't be "black-translucent" (see
  // index.html's comment - it breaks the installed WebView's height on
  // iOS), so the status bar is always opaque there. "default" is a light
  // opaque bar and "black" a dark one; matching it to the current theme at
  // least keeps that opaque bar from reading as a mismatched black band on
  // top of the light theme's --bg (#f2f2f7). Best-effort only: like other
  // apple-mobile-web-app-* tags, iOS freezes whatever this held at
  // "Add to Home Screen" time, so a later theme switch won't reach an
  // already-installed icon until it's re-added.
  const statusBar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]')
  if (statusBar) statusBar.setAttribute('content', effectiveScheme(pref) === 'dark' ? 'black' : 'default')
}

/** Persists the user's theme choice and applies it as `data-theme` on <html>,
 * which index.css keys off (falling back to `prefers-color-scheme` for
 * "system"). Also re-applies on OS theme changes while set to "system". */
export function useTheme() {
  const [theme, setTheme] = useState<ThemePreference>(getStoredTheme)

  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Storage unavailable (private mode, quota) - theme still applies for this session.
    }
  }, [theme])

  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  return { theme, setTheme }
}
