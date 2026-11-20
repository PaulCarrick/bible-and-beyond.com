import type { SiteSettings } from './types'

// Several domains serve this same site from one server (see "Second domain: freestudy.bible" in CLAUDE.md). The title
// set on the Drupal Site settings screen is the main domain's; a domain listed here shows its own name instead, in the
// header, the browser tab, the welcome page and the pages that name the site. Emails, texts and the Drupal admin keep
// the Site settings title, since they are not tied to the domain a visitor came in on.
const domainTitles: Record<string, string> = {
  'freestudy.bible': 'Free Study Bible',
}

// This domain's own name, or null when it uses the title from Site settings. "www." is ignored.
export function domainTitle(hostname: string = window.location.hostname): string | null {
  const name = hostname.toLowerCase().replace(/^www\./, '')
  return domainTitles[name] ?? null
}

// The settings as this domain shows them: its own name for the title, and in the welcome paragraph wherever the
// Site settings title appears (the paragraph is written by an administrator and usually names the site).
export function settingsForThisDomain(settings: SiteSettings, hostname?: string): SiteSettings {
  const title = domainTitle(hostname)
  if (title === null || title === settings.title) {
    return settings
  }
  const welcomeHtml = settings.welcome_html && settings.title
    ? settings.welcome_html.split(settings.title).join(title)
    : settings.welcome_html
  return { ...settings, title, welcome_html: welcomeHtml }
}
