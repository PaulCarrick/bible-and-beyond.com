// Every time zone the browser knows, sorted, with UTC and the visitor's own always in it. Used by the daily
// email choosers (devotionals and the prayer list).
export function allTimeZones(): string[] {
  const own = Intl.DateTimeFormat().resolvedOptions().timeZone
  const names = new Set<string>(Intl.supportedValuesOf('timeZone'))
  names.add('UTC')
  if (own) {
    names.add(own)
  }
  return [...names].sort()
}

// The visitor's own time zone, or UTC when the browser does not say.
export function ownTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}
