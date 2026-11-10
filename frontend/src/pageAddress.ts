import type { View } from './views'

// Each page's address, so a page can be reloaded, bookmarked or shared, and the browser's Back and Forward
// buttons move between pages. The server sends the site for any address (nginx try_files).
// The pages reached from an emailed link (reset a password, confirm an address, stop emails) carry a token, so
// they have no address of their own: a reload there goes to the welcome page.
const addresses: Record<View, string> = {
  welcome: '/',
  read: '/read',
  bible: '/search',
  commentary: '/search-commentaries',
  browse: '/browse-commentaries',
  devotionals: '/devotionals',
  books: '/books',
  searchBooks: '/search-books',
  music: '/music',
  searchMusic: '/search-music',
  searchAll: '/search-all',
  faq: '/faq',
  help: '/help',
  contact: '/contact',
  copyright: '/copyright',
  notes: '/notes',
  register: '/register',
  login: '/login',
  forgot: '/forgot-password',
  reset: '/',
  verify: '/',
  unsubscribe: '/',
}

export function addressFor(view: View): string {
  return addresses[view]
}

// The page an address names; the welcome page for "/" or an address the site does not have.
export function viewForAddress(pathname: string): View {
  const path = pathname.replace(/\/+$/, '') || '/'
  const found = (Object.keys(addresses) as View[]).find((view) => addresses[view] === path && path !== '/')
  return found ?? 'welcome'
}

// What the site keeps in each browser history entry: the page, and a number for the entry so its scroll place
// can be found again. Nothing is stored beyond the tab's own history.
export interface PageHistoryState {
  view: View
  entry: number
}

export function readPageHistoryState(state: unknown): PageHistoryState | null {
  if (state && typeof state === 'object' && 'view' in state && 'entry' in state) {
    const { view, entry } = state as PageHistoryState
    if (view in addresses && typeof entry === 'number') {
      return { view, entry }
    }
  }
  return null
}
