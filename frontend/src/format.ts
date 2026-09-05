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
