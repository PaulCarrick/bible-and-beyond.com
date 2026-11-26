import pageInfo from './pageInfo.json'
import type { View } from './views'

// A public page's own name ("Read the Bible"), from pageInfo.json, which also gives each page's HTML its title
// (scripts/make-page-files.mjs). Empty for the welcome page and for pages not listed there: the tab then shows only
// the site's title.
export function pageTitleFor(view: View): string {
  const info = (pageInfo as Record<string, { title: string }>)[view]
  return info ? info.title : ''
}
