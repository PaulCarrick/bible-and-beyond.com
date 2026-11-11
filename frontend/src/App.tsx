import { useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import {
  fetchBooks,
  fetchCommentarySources,
  fetchCurrentUser,
  fetchDevotionals,
  fetchMusic,
  fetchOtherBooks,
  fetchSiteSettings,
  fetchTranslations,
  logOut,
  resendVerification,
} from './api'
import type { MusicSong } from './api'
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
import BookSearchPage from './BookSearchPage'
import MusicPage from './MusicPage'
import MusicSearchPage from './MusicSearchPage'
import FaqPage from './FaqPage'
import HelpPage from './HelpPage'
import TutorialPage from './TutorialPage'
import DevotionalsTab from './DevotionalsTab'
import SearchTab from './SearchTab'
import SideNav from './SideNav'
import type { NavGroup } from './SideNav'
import SiteFooter from './SiteFooter'
import SiteTooltip from './SiteTooltip'
import SiteHeader from './SiteHeader'
import WelcomePage from './WelcomePage'
import WelcomeSearch from './WelcomeSearch'
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
  // An address such as /faq?question=... (a link to another answer in a note from the site owner, opened in a
  // new tab). It is read here because the address is tidied to /faq before the FAQ page first draws.
  const [faqQuestionLink] = useState(() =>
    viewForAddress(window.location.pathname) === 'faq' ? new URLSearchParams(window.location.search).get('question') : null,
  )
  // An address such as /books?book=apostles-creed: the Other books reader at the start of that book (a link from
  // an FAQ note, another site or a bookmark). Read here, before the address is tidied to /books.
  const [bookLink] = useState((): Destination | null => {
    const book = new URLSearchParams(window.location.search).get('book') ?? ''
    if (viewForAddress(window.location.pathname) !== 'books' || !/^[a-z0-9-]{3,50}$/.test(book)) {
      return null
    }
    return { id: Date.now(), kind: 'devotional', devotional: book, section: -1, unit: -1, onlyIfFound: true }
  })
  // The song a /music?song=amazing-grace address names, shown when the music page opens (read here, before the
  // address is tidied to /music). The search page's "Play this song" sets it too, with a new key each time.
  const [musicFocus, setMusicFocus] = useState<{ id: string; key: number } | null>(() => {
    const song = new URLSearchParams(window.location.search).get('song') ?? ''
    return viewForAddress(window.location.pathname) === 'music' && /^[a-z0-9-]{3,50}$/.test(song) ? { id: song, key: Date.now() } : null
  })
  // The published songs of the Christian music section; its sidebar group shows only when there are some.
  const [songs, setSongs] = useState<MusicSong[]>([])
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [devotionals, setDevotionals] = useState<DevotionalInfo[]>([])
  // The Other books: read by chapter like a devotional, on their own page.
  const [otherBooks, setOtherBooks] = useState<DevotionalInfo[]>([])
  const [siteSettings, setSiteSettings] = useState<SiteSettings>(defaultSiteSettings)
  const [user, setUser] = useState<AccountUser | null>(null)
  const [resendMessage, setResendMessage] = useState('')
  // Where a note's link asked a reader to open, with a new id each time.
  const [destination, setDestination] = useState<Destination | null>(verseLink ?? bookLink)
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
    fetchOtherBooks()
      .then(setOtherBooks)
      .catch(() => setOtherBooks([]))
    fetchMusic()
      .then(setSongs)
      .catch(() => setSongs([]))
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
      // A note on an Other book is kept like one on a devotional reading; it opens in the books' reader.
      navigate(otherBooks.some((book) => book.id === note.source_code) ? 'books' : 'devotionals')
    }
  }

  // Open a page: a new history entry (unless it is the page already shown), at the top.
  // Whether a reading named by a link belongs to the Other books (else it is a devotional's).
  function isOtherBook(id: string) {
    return otherBooks.some((book) => book.id === id)
  }

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
    {
      entries: [
        { view: 'welcome', label: 'Welcome' },
        { view: 'searchAll', label: 'Search everything' },
      ],
    },
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
    ...(otherBooks.length > 0
      ? [
          {
            heading: 'Other books',
            entries: [
              { view: 'books' as View, label: 'Read other books' },
              { view: 'searchBooks' as View, label: 'Search other books' },
            ],
          },
        ]
      : []),
    ...(songs.length > 0
      ? [
          {
            heading: 'Christian music',
            entries: [
              { view: 'music' as View, label: 'Listen to the music' },
              { view: 'searchMusic' as View, label: 'Search the music' },
            ],
          },
        ]
      : []),
    // The FAQ is about the faith, not about this site, so it has a group of its own rather than sitting under About.
    { heading: 'Questions', entries: [{ view: 'faq' as View, label: 'FAQ' }] },
    {
      heading: 'About',
      entries: [
        { view: 'help' as View, label: 'Help' },
        { view: 'tutorial' as View, label: 'Tutorial video' },
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
                  otherBooks={otherBooks}
                  songs={songs}
                  onNavigate={navigate}
                />
              )}
              {/* Below the welcome cards, and a page of its own (Search everything in the sidebar): one search, so the
                  words and hits are the same on both. Kept mounted so its hits are still there after going Back. */}
              <WelcomeSearch
                isHidden={activeView !== 'welcome' && activeView !== 'searchAll'}
                isPage={activeView === 'searchAll'}
                onOpen={(found, view) => {
                  setDestination(found)
                  navigate(view)
                }}
                onOpenSong={(songId) => {
                  setMusicFocus({ id: songId, key: Date.now() })
                  navigate('music')
                }}
              />
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
              {activeView === 'help' && <HelpPage translations={translations} onNavigate={navigate} hasMusic={songs.length > 0} />}
              {activeView === 'tutorial' && <TutorialPage onNavigate={navigate} />}
              {activeView === 'copyright' && (
                <CopyrightPage onBack={() => navigate('help')} devotionals={[...devotionals, ...otherBooks]} commentaries={commentaries} />
              )}

              {/* The form stays mounted too, so a half-written message is not lost. */}
              <ContactPage isHidden={activeView !== 'contact'} />
              {/* The FAQ stays mounted too, so the answers it has shown are kept. */}
              <FaqPage isHidden={activeView !== 'faq'} initialQuestion={faqQuestionLink} />

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
                <DevotionalsTab
                  devotionals={devotionals}
                  translations={translations}
                  isHidden={activeView !== 'devotionals'}
                  destination={destination?.kind === 'devotional' && isOtherBook(destination.devotional) ? null : destination}
                />
              )}
              {otherBooks.length > 0 && (
                <DevotionalsTab
                  collection="books"
                  devotionals={otherBooks}
                  translations={translations}
                  isHidden={activeView !== 'books'}
                  destination={destination?.kind === 'devotional' && isOtherBook(destination.devotional) ? destination : null}
                />
              )}
              {otherBooks.length > 0 && (
                <BookSearchPage
                  books={otherBooks}
                  isHidden={activeView !== 'searchBooks'}
                  onOpen={(book, section, unit) => {
                    setDestination({ id: Date.now(), kind: 'devotional', devotional: book, section, unit })
                    navigate('books')
                  }}
                />
              )}
              {songs.length > 0 && (
                <>
                  <MusicPage songs={songs} isHidden={activeView !== 'music'} focus={musicFocus} />
                  <MusicSearchPage
                    isHidden={activeView !== 'searchMusic'}
                    onOpen={(songId) => {
                      setMusicFocus({ id: songId, key: Date.now() })
                      navigate('music')
                    }}
                  />
                </>
              )}
            </main>

            <SiteFooter copyrightText={siteSettings.copyright} />
          </div>
        </div>
      </div>
      <SiteTooltip />
    </AccountContext.Provider>
  )
}

export default App
