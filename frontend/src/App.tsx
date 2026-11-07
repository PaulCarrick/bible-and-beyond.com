import { useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import {
  fetchBooks,
  fetchCommentarySources,
  fetchCurrentUser,
  fetchDevotionals,
  fetchSiteSettings,
  fetchTranslations,
  logOut,
  resendVerification,
} from './api'
import BibleTab from './BibleTab'
import BrowseTab from './BrowseTab'
import { AccountContext } from './AccountContext'
import { chooseContextTranslation } from './contextTranslation'
import NotesPage from './NotesPage'
import AccountPage from './AccountPage'
import UnsubscribePage from './UnsubscribePage'
import VerifyEmailPage from './VerifyEmailPage'
import ContactPage from './ContactPage'
import CopyrightPage from './CopyrightPage'
import FaqPage from './FaqPage'
import HelpPage from './HelpPage'
import DevotionalsTab from './DevotionalsTab'
import SearchTab from './SearchTab'
import SideNav from './SideNav'
import type { NavGroup } from './SideNav'
import SiteFooter from './SiteFooter'
import SiteHeader from './SiteHeader'
import WelcomePage from './WelcomePage'
import { readVerseAddress } from './verseAddress'
import { addressFor, readPageHistoryState, viewForAddress } from './pageAddress'
import type { PageHistoryState } from './pageAddress'
import type { Book, CommentarySource, DevotionalInfo, SiteSettings, Translation } from './types'
import type { AccountUser, Destination, Note } from './types'
import type { View } from './views'
import './App.css'

// What the pages show until the administrator's settings arrive, and if they cannot be had.
const defaultSiteSettings: SiteSettings = {
  title: 'Bible and Beyond',
  copyright: 'Copyright © 2026 by Paul Carrick. All Rights Reserved.',
}

// The links in our emails open the site with ?verify=..., ?reset=... or ?unsubscribe=... on the end.
function readEmailLink(): { kind: 'verify' | 'reset' | 'unsubscribe'; token: string } | null {
  const parameters = new URLSearchParams(window.location.search)
  for (const kind of ['verify', 'reset', 'unsubscribe'] as const) {
    const token = parameters.get(kind)
    if (token) {
      return { kind, token }
    }
  }
  return null
}

function App() {
  const [emailLink] = useState(readEmailLink)
  // An address such as /?read=BSB&book=62&chapter=4&verse=1 (the FAQ's verse links, opened in a new tab).
  const [verseLink] = useState(() => readVerseAddress(window.location.search))
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [devotionals, setDevotionals] = useState<DevotionalInfo[]>([])
  const [siteSettings, setSiteSettings] = useState<SiteSettings>(defaultSiteSettings)
  const [user, setUser] = useState<AccountUser | null>(null)
  const [resendMessage, setResendMessage] = useState('')
  // Where a note's link asked a reader to open, with a new id each time.
  const [destination, setDestination] = useState<Destination | null>(verseLink)
  const [loadErrorMessage, setLoadErrorMessage] = useState('')
  // The page the visit opens on: an emailed link's page, the reader for a verse address, else the page the
  // address names (/help, /faq, ...).
  const [initialView] = useState<View>(
    () => emailLink?.kind ?? (verseLink ? 'read' : viewForAddress(window.location.pathname)),
  )
  const [activeView, setActiveView] = useState<View>(initialView)
  // Each page visited is an entry in the browser's history (only for this tab, nothing is stored), so Back
  // and Forward move between pages. Where each entry was scrolled to is kept here, by entry number.
  const scrollPlaces = useRef(new Map<number, number>())
  // The first history entry is the page the visit opened on, at that page's own address. It is set before
  // anything can be clicked, so a quick first click cannot be overwritten. An emailed link's token is taken
  // out of the address so it is not bookmarked or shared by mistake, and a verse address is too, because the
  // reader moves on from it.
  const [firstEntry] = useState(() => {
    const state: PageHistoryState = { view: initialView, entry: Date.now() }
    window.history.scrollRestoration = 'manual'
    window.history.replaceState(state, '', addressFor(initialView))
    return state.entry
  })
  const currentEntry = useRef(firstEntry)
  // On a phone the sidebar is a menu under the header.
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  useEffect(() => {
    Promise.all([fetchTranslations(), fetchBooks(), fetchCommentarySources()])
      .then(([loadedTranslations, loadedBooks, loadedCommentaries]) => {
        setTranslations(loadedTranslations)
        setBooks(loadedBooks)
        setCommentaries(loadedCommentaries)
      })
      .catch((error) =>
        setLoadErrorMessage(error instanceof Error ? error.message : 'Could not load Bible data'),
      )
  }, [])

  // The devotionals are optional: their entry only appears when there are some, and a failure to load
  // them must not stop the rest of the site.
  useEffect(() => {
    fetchDevotionals()
      .then(setDevotionals)
      .catch(() => setDevotionals([]))
  }, [])

  // The title and the copyright line are set in the Drupal admin. A failure to load them must not stop
  // the site: it shows the ones it started with.
  useEffect(() => {
    fetchSiteSettings()
      .then(setSiteSettings)
      .catch(() => setSiteSettings(defaultSiteSettings))
  }, [])

  // On Back or Forward, show that entry's page at the place it was scrolled to when it was left. The pages stay
  // mounted, so their contents (search results, the chapter being read) are as they were.
  useEffect(() => {
    function showHistoryEntry(event: PopStateEvent) {
      scrollPlaces.current.set(currentEntry.current, window.scrollY)
      const state = readPageHistoryState(event.state)
      currentEntry.current = state?.entry ?? Date.now()
      const place = scrollPlaces.current.get(currentEntry.current) ?? 0
      // The page has to be on screen before it can be scrolled to its place.
      flushSync(() => {
        setActiveView(state?.view ?? viewForAddress(window.location.pathname))
        setIsMenuOpen(false)
      })
      window.scrollTo(0, place)
    }
    window.addEventListener('popstate', showHistoryEntry)
    return () => window.removeEventListener('popstate', showHistoryEntry)
  }, [])

  // Whether a visitor is logged in (the browser sends its session cookie). Nobody has to be.
  useEffect(() => {
    fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
  }, [])

  useEffect(() => {
    document.title = siteSettings.title
  }, [siteSettings.title])

  const handleVerified = useCallback((verifiedUser: AccountUser | null) => setUser(verifiedUser), [])

  // The link on a note: open the reader that shows what the note is about, at that place.
  function openNoteItem(note: Note) {
    const id = Date.now()
    if (note.item_type === 'bible_verse') {
      setDestination({
        id,
        kind: 'bible',
        translation: note.source_code,
        book: note.book_number ?? 1,
        chapter: note.chapter ?? 1,
        verse: note.verse ?? 1,
      })
      navigate('read')
    } else if (note.item_type === 'commentary') {
      setDestination({
        id,
        kind: 'commentary',
        commentary: note.source_code,
        book: note.book_number ?? 1,
        chapter: note.chapter ?? 1,
        verse: note.verse ?? 1,
      })
      navigate('browse')
    } else {
      setDestination({ id, kind: 'devotional', devotional: note.source_code, section: note.section ?? 0, unit: note.unit ?? 1 })
      navigate('devotionals')
    }
  }

  // Open a page: a new history entry (unless it is the page already shown), at the top.
  function navigate(view: View) {
    if (view !== readPageHistoryState(window.history.state)?.view) {
      // Where the page being left was scrolled to, for coming back to it.
      scrollPlaces.current.set(currentEntry.current, window.scrollY)
      currentEntry.current = Math.max(Date.now(), currentEntry.current + 1)
      const state: PageHistoryState = { view, entry: currentEntry.current }
      window.history.pushState(state, '', addressFor(view))
    }
    setActiveView(view)
    setIsMenuOpen(false)
    window.scrollTo(0, 0)
  }

  // The commentaries and the devotionals only appear in the sidebar once there are some.
  const navGroups: NavGroup[] = [
    { entries: [{ view: 'welcome', label: 'Welcome' }] },
    {
      heading: 'Bible',
      entries: [
        { view: 'read', label: 'Read the Bible' },
        { view: 'bible', label: 'Search the Bible' },
      ],
    },
    ...(commentaries.length > 0
      ? [
          {
            heading: 'Commentaries',
            entries: [
              { view: 'browse' as View, label: 'Read the commentaries' },
              { view: 'commentary' as View, label: 'Search the commentaries' },
            ],
          },
        ]
      : []),
    ...(devotionals.length > 0
      ? [{ heading: 'Devotionals', entries: [{ view: 'devotionals' as View, label: 'Read the devotionals' }] }]
      : []),
    // The FAQ is about the faith, not about this site, so it has a group of its own rather than sitting under About.
    { heading: 'Questions', entries: [{ view: 'faq' as View, label: 'FAQ' }] },
    {
      heading: 'About',
      entries: [
        { view: 'help' as View, label: 'Help' },
        { view: 'contact' as View, label: 'Contact' },
      ],
    },
  ]

  return (
    <AccountContext.Provider value={{ user, onNavigate: navigate }}>
      <div className="app-shell">
        <SiteHeader
          title={siteSettings.title}
          isMenuOpen={isMenuOpen}
          onToggleMenu={() => setIsMenuOpen(!isMenuOpen)}
          onGoHome={() => navigate('welcome')}
          user={user}
          onSetUpAccount={() => navigate('register')}
          onShowNotes={() => navigate('notes')}
          onLogIn={() => navigate('login')}
          onLogOut={() => {
            logOut()
              .catch(() => undefined)
              .finally(() => {
                setUser(null)
                navigate('welcome')
              })
          }}
        />

        <div className="site-body">
          <SideNav groups={navGroups} activeView={activeView} isOpen={isMenuOpen} onNavigate={navigate} />

          {/* The page content and the footer share the column to the right of the sidebar. */}
          <div className="site-column">
            <main className="site-main" id="content">
              {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}

              {activeView === 'welcome' && (
                <WelcomePage
                siteTitle={siteSettings.title}
                  translations={translations}
                  commentaries={commentaries}
                  devotionals={devotionals}
                  onNavigate={navigate}
                />
              )}
              {user && !user.email_verified && activeView !== 'verify' && (
                <p className="contact-sent" role="status">
                  Please confirm your email address: we sent a link to {user.email}.{' '}
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => {
                      setResendMessage('')
                      resendVerification()
                        .then(() => setResendMessage('Sent. If it does not arrive in a few minutes, check your spam folder.'))
                        .catch((error: Error) => setResendMessage(error.message))
                    }}
                  >
                    Send it again
                  </button>{' '}
                  {resendMessage}
                </p>
              )}
              {activeView === 'notes' && <NotesPage books={books} translation={chooseContextTranslation(translations)} onOpenItem={openNoteItem} />}
            {activeView === 'unsubscribe' && emailLink && <UnsubscribePage token={emailLink.token} />}
            {activeView === 'verify' && emailLink && (
                <VerifyEmailPage token={emailLink.token} onVerified={handleVerified} />
              )}
              {(activeView === 'register' || activeView === 'login' || activeView === 'forgot' || activeView === 'reset') && (
                <AccountPage
                  key={activeView}
                  mode={activeView}
                  token={emailLink?.token ?? ''}
                  onDone={(loggedInUser) => {
                    setUser(loggedInUser)
                    navigate('welcome')
                  }}
                  onNavigate={navigate}
                />
              )}
              {activeView === 'help' && <HelpPage translations={translations} onNavigate={navigate} />}
              {activeView === 'copyright' && (
                <CopyrightPage onBack={() => navigate('help')} devotionals={devotionals} commentaries={commentaries} />
              )}

              {/* The form stays mounted too, so a half-written message is not lost. */}
              <ContactPage isHidden={activeView !== 'contact'} />
              {/* The FAQ stays mounted too, so the answers it has shown are kept. */}
              <FaqPage isHidden={activeView !== 'faq'} />

              {/* The readers and searches stay mounted while another page is open, so nothing is lost. */}
              <BibleTab translations={translations} isHidden={activeView !== 'read'} destination={destination} />
              <SearchTab
                mode="bible"
                translations={translations}
                books={books}
                commentaries={commentaries}
                isHidden={activeView !== 'bible'}
                onShowCopyrights={() => navigate('copyright')}
              />
              {commentaries.length > 0 && (
                <>
                  <SearchTab
                    mode="commentary"
                    translations={translations}
                    books={books}
                    commentaries={commentaries}
                    isHidden={activeView !== 'commentary'}
                    onShowCopyrights={() => navigate('copyright')}
                  />
                  <BrowseTab commentaries={commentaries} translations={translations} isHidden={activeView !== 'browse'} destination={destination} />
                </>
              )}
              {devotionals.length > 0 && (
                <DevotionalsTab devotionals={devotionals} translations={translations} isHidden={activeView !== 'devotionals'} destination={destination} />
              )}
            </main>

            <SiteFooter copyrightText={siteSettings.copyright} />
          </div>
        </div>
      </div>
    </AccountContext.Provider>
  )
}

export default App
