import { useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import {
  fetchBooks,
  fetchCommentarySources,
  fetchCurrentUser,
  fetchDevotionals,
  fetchExternalSites,
  fetchKindleBooks,
  fetchMaps,
  fetchMusic,
  fetchOtherBooks,
  fetchSiteSettings,
  siteIconAddress,
  fetchTranslations,
  logOut,
  resendVerification,
} from './api'
import type { ExternalSite, KindleBook, MapInfo, MusicSong } from './api'
import KindleShelf from './KindleShelf'
import BibleTab from './BibleTab'
import BrowseTab from './BrowseTab'
import { AccountContext } from './AccountContext'
import { chooseContextTranslation } from './contextTranslation'
import NotesPage from './NotesPage'
import MyListsPage from './MyListsPage'
import PublicListsPage from './PublicListsPage'
import type { SavedListEntry } from './api'
import ConversationsPage from './ConversationsPage'
import AccountPage from './AccountPage'
import UnsubscribePage from './UnsubscribePage'
import MessageRequestPage from './MessageRequestPage'
import VerifyEmailPage from './VerifyEmailPage'
import ContactPage from './ContactPage'
import CopyrightPage from './CopyrightPage'
import BookSearchPage from './BookSearchPage'
import MusicPage from './MusicPage'
import MusicSearchPage from './MusicSearchPage'
import MapsPage from './MapsPage'
import MapSearchPage from './MapSearchPage'
import FaqPage from './FaqPage'
import HelpPage from './HelpPage'
import TutorialPage from './TutorialPage'
import ExternalSitesPage from './ExternalSitesPage'
import DayCardPage from './DayCardPage'
import PrivacyPage from './PrivacyPage'
import SmsTermsPage from './SmsTermsPage'
import PostingPolicyPage from './PostingPolicyPage'
import MyAccountPage from './MyAccountPage'
import ConfirmPhoneBox from './ConfirmPhoneBox'
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
import type { VerseInBible } from './verseAddress'
import { addressFor, readPageHistoryState, viewForAddress } from './pageAddress'
import { settingsForThisDomain } from './domainTitle'
import type { PageHistoryState } from './pageAddress'
import type { Book, CommentarySource, DevotionalInfo, SiteSettings, Translation } from './types'
import type { AccountUser, Destination, Note } from './types'
import type { View } from './views'
import './App.css'

// What the pages show until the administrator's settings arrive, and if they cannot be had.
// The pages a visitor who is not logged in may open while "Login required" is on. Not Set up account: then only an
// administrator sets up accounts (Site users), and the API refuses sign-ups.
const lockedOutViews: View[] = ['login', 'forgot', 'reset', 'verify', 'unsubscribe', 'messageRequest', 'privacy', 'smsTerms', 'postingPolicy']

// A domain with its own name (domainTitle.ts) shows that name instead of the title.
const defaultSiteSettings: SiteSettings = settingsForThisDomain({
  title: 'Bible and Beyond',
  copyright: 'Copyright © 2026 by Paul Carrick. All Rights Reserved.',
})

// The links in our emails open the site with ?verify=..., ?reset=..., ?unsubscribe=... or ?message-request=...
// (a request to send the member posts, 2026-11-23) on the end.
function readEmailLink(): { kind: 'verify' | 'reset' | 'unsubscribe' | 'messageRequest'; token: string } | null {
  const parameters = new URLSearchParams(window.location.search)
  for (const kind of ['verify', 'reset', 'unsubscribe'] as const) {
    const token = parameters.get(kind)
    if (token) {
      return { kind, token }
    }
  }
  const request = parameters.get('message-request')
  return request ? { kind: 'messageRequest', token: request } : null
}

function App() {
  const [emailLink] = useState(readEmailLink)
  // An address such as /?read=BSB&book=62&chapter=4&verse=1 (the FAQ's verse links, opened in a new tab).
  const [verseLink] = useState(() => readVerseAddress(window.location.search))
  // An address such as /faq?question=... (a link to another answer in a note from the site owner, opened in a
  // new tab). It is read here because the address is tidied to /faq before the FAQ page first draws.
  // A hit of Search everything asks for a question in the same way, with a new id each time.
  const [faqRequest, setFaqRequest] = useState<{ question: string; id: number } | null>(() => {
    const question = viewForAddress(window.location.pathname) === 'faq' ? new URLSearchParams(window.location.search).get('question') : null
    return question ? { question, id: 0 } : null
  })
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
  // A shared playlist to play on the music page (Play on Public lists), with a new key each time.
  const [musicPlayRequest, setMusicPlayRequest] = useState<{ name: string; songIds: string[]; key: number } | null>(null)
  // The shared playlist a /public-lists?playlist=12 address names (a link sent from Copy link), opened when Public
  // lists opens (read here, before the address is tidied to /public-lists).
  const [publicPlaylistFocus] = useState<number | null>(() => {
    const playlist = new URLSearchParams(window.location.search).get('playlist') ?? ''
    return viewForAddress(window.location.pathname) === 'publicLists' && /^[0-9]{1,12}$/.test(playlist) ? Number(playlist) : null
  })
  // The map a /maps?map=pauls-journeys address names, shown when the maps page opens (read here, before the
  // address is tidied to /maps). The search pages' "Open this map" sets it too, with a new key each time.
  const [mapFocus, setMapFocus] = useState<{ id: string; key: number } | null>(() => {
    const map = new URLSearchParams(window.location.search).get('map') ?? ''
    return viewForAddress(window.location.pathname) === 'maps' && /^[a-z0-9-]{3,50}$/.test(map) ? { id: map, key: Date.now() } : null
  })
  // The published maps; their sidebar group shows only when there are some.
  const [maps, setMaps] = useState<MapInfo[]>([])
  // The external sites the administrators chose to show; their sidebar group shows only when there are some.
  const [externalSites, setExternalSites] = useState<ExternalSite[]>([])
  // Books in Amazon's Kindle reader, listed with the Devotionals or the Other books (KindleShelf).
  const [kindleBooks, setKindleBooks] = useState<KindleBook[]>([])
  // The published songs of the Christian music section; its sidebar group shows only when there are some.
  const [songs, setSongs] = useState<MusicSong[]>([])
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [devotionals, setDevotionals] = useState<DevotionalInfo[]>([])
  // The Other books: read by chapter like a devotional, on their own page.
  const [otherBooks, setOtherBooks] = useState<DevotionalInfo[]>([])
  const [siteSettings, setSiteSettings] = useState<SiteSettings>(defaultSiteSettings)
  // Until the settings arrive the header leaves the emblem's place empty, so a replaced emblem never flashes
  // the site's own first.
  const [areSettingsLoaded, setAreSettingsLoaded] = useState(false)
  const [user, setUser] = useState<AccountUser | null>(null)
  // Whether the first "who is logged in" answer has come (so My account does not say "log in" while it loads).
  const [isAccountKnown, setIsAccountKnown] = useState(false)
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
    fetchMaps()
      .then(setMaps)
      .catch(() => setMaps([]))
    fetchExternalSites()
      .then(setExternalSites)
      .catch(() => setExternalSites([]))
    fetchKindleBooks()
      .then(setKindleBooks)
      .catch(() => setKindleBooks([]))
  }, [])

  // The title and the copyright line are set in the Drupal admin. A failure to load them must not stop
  // the site: it shows the ones it started with.
  useEffect(() => {
    fetchSiteSettings()
      .then((settings) => setSiteSettings(settingsForThisDomain(settings)))
      .catch(() => setSiteSettings(defaultSiteSettings))
      .finally(() => setAreSettingsLoaded(true))
  }, [])

  // The browser-tab icon: an uploaded one replaces the site's own (index.html links /favicon.svg).
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    if (!link) {
      return
    }
    if (siteSettings.tab_icon) {
      link.removeAttribute('type')
      link.href = siteIconAddress(siteSettings.tab_icon)
    } else {
      link.type = 'image/svg+xml'
      link.href = '/favicon.svg'
    }
  }, [siteSettings.tab_icon])

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

  // Set when the visitor has just closed their account (My account then says so instead of "please log in").
  const [wasAccountClosed, setWasAccountClosed] = useState(false)

  // Whether a visitor is logged in (the browser sends its session cookie). Nobody has to be.
  useEffect(() => {
    fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsAccountKnown(true))
  }, [])

  useEffect(() => {
    document.title = siteSettings.title
  }, [siteSettings.title])

  // "Login required" (Site settings): until a visitor logs in, only the sign-in pages are shown (the API refuses the
  // rest). Logging in then reloads the page, so everything the site lists is loaded for the account.
  const isLockedOut = areSettingsLoaded && isAccountKnown && siteSettings.login_required === true && user === null
  const wasLockedOut = useRef(false)
  useEffect(() => {
    if (wasLockedOut.current && !isLockedOut) {
      window.location.assign(addressFor('welcome'))
    }
    wasLockedOut.current = isLockedOut
  }, [isLockedOut])
  const lockedOutView: View = lockedOutViews.includes(activeView) ? activeView : 'login'

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
    } else if (note.item_type === 'map') {
      openMap(note.source_code)
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

  // An entry of My lists, opened where it came from.
  function openListEntry(entry: SavedListEntry) {
    const id = Date.now()
    const target = entry.target
    if (entry.kind === 'bible') {
      setDestination({ id, kind: 'bible', translation: target.translation ?? '', book: target.book ?? 1, chapter: target.chapter ?? 1, verse: target.verse ?? 1 })
      navigate('read')
    } else if (entry.kind === 'commentary') {
      setDestination({ id, kind: 'commentary', commentary: target.commentary ?? '', book: target.book ?? 1, chapter: target.chapter ?? 1, verse: target.verse ?? 1 })
      navigate('browse')
    } else if (entry.kind === 'devotional' || entry.kind === 'book') {
      const devotional = target.devotional ?? ''
      setDestination({ id, kind: 'devotional', devotional, section: target.section ?? 0, unit: target.unit ?? 1 })
      navigate(isOtherBook(devotional) ? 'books' : 'devotionals')
    } else if (entry.kind === 'music') {
      setMusicFocus({ id: target.song ?? '', key: id })
      navigate('music')
    } else if (entry.kind === 'map') {
      openMap(target.map ?? '')
    } else {
      setFaqRequest({ question: target.question ?? entry.title, id })
      navigate('faq')
    }
  }

  // A verse link on a map: the Bible reader at that verse.
  function openVerse(verse: VerseInBible) {
    setDestination({ id: Date.now(), kind: 'bible', ...verse })
    navigate('read')
  }

  function openMap(mapId: string) {
    setMapFocus({ id: mapId, key: Date.now() })
    navigate('maps')
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

  const kindleDevotionals = kindleBooks.filter((book) => book.collection === 'devotionals')
  const kindleOtherBooks = kindleBooks.filter((book) => book.collection === 'books')

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
    // A collection with only Kindle books still has its entry (there is nothing to search in them).
    ...(devotionals.length > 0 || kindleDevotionals.length > 0
      ? [{ heading: 'Devotionals', entries: [{ view: 'devotionals' as View, label: 'Read the devotionals' }] }]
      : []),
    ...(otherBooks.length > 0 || kindleOtherBooks.length > 0
      ? [
          {
            heading: 'Other books',
            entries: [
              { view: 'books' as View, label: 'Read other books' },
              ...(otherBooks.length > 0 ? [{ view: 'searchBooks' as View, label: 'Search other books' }] : []),
            ],
          },
        ]
      : []),
    ...(songs.length > 0
      ? [
          {
            heading: 'Christian media',
            entries: [
              { view: 'music' as View, label: 'Listen to the media' },
              { view: 'searchMusic' as View, label: 'Search the media' },
            ],
          },
        ]
      : []),
    ...(maps.length > 0
      ? [
          {
            heading: 'Maps',
            entries: [
              { view: 'maps' as View, label: 'View the maps' },
              { view: 'searchMaps' as View, label: 'Search the maps' },
            ],
          },
        ]
      : []),
    // Other sites the administrators set up and chose to show (the Drupal "External sites" page): only when there are
    // some (the owner's request, 2026-11-19).
    ...(externalSites.length > 0
      ? [{ heading: 'External sites', entries: [{ view: 'externalSites' as View, label: 'Other sites we use' }] }]
      : []),
    // The FAQ is about the faith, not about this site, so it has a group of its own rather than sitting under About.
    { heading: 'Questions', entries: [{ view: 'faq' as View, label: 'FAQ' }] },
    // A picture of a random verse, and of today's reading of a daily devotional (DayCardPage.tsx).
    {
      heading: 'Today',
      entries: [
        { view: 'verseOfTheDay' as View, label: 'Verse of the day' },
        ...(devotionals.some((devotional) => devotional.kind === 'daily')
          ? [{ view: 'devotionalOfTheDay' as View, label: 'Devotional of the day' }]
          : []),
      ],
    },
    // Everyone may read Conversations and the Prayer Wall; only accounts an administrator allowed (use_conversations)
    // may write. The two keep their posts apart (a board on each post).
    {
      heading: 'Members',
      entries: [
        { view: 'conversations' as View, label: 'Conversations' },
        { view: 'prayerWall' as View, label: 'Prayer Wall' },
        // Lists members shared from My lists (accounts allowed share_lists); everyone may read them.
        { view: 'publicLists' as View, label: 'Public lists' },
      ],
    },
    {
      heading: 'About',
      entries: [
        { view: 'help' as View, label: 'Help' },
        { view: 'tutorial' as View, label: 'Tutorial video' },
        { view: 'contact' as View, label: 'Contact' },
        { view: 'privacy' as View, label: 'Privacy' },
        { view: 'smsTerms' as View, label: 'Text message terms' },
        { view: 'postingPolicy' as View, label: 'Posting policy' },
      ],
    },
  ]

  return (
    <AccountContext.Provider value={{ user, onNavigate: navigate }}>
      <div className="app-shell">
        <SiteHeader
          title={siteSettings.title}
          iconAddress={!areSettingsLoaded ? null : siteSettings.header_icon ? siteIconAddress(siteSettings.header_icon) : '/logo-icon.svg'}
          isMenuOpen={isMenuOpen}
          onToggleMenu={() => setIsMenuOpen(!isMenuOpen)}
          onGoHome={() => navigate('welcome')}
          user={user}
          onSetUpAccount={() => navigate('register')}
          canSetUpAccount={!siteSettings.login_required}
          onShowNotes={() => navigate('notes')}
          onShowLists={() => navigate('lists')}
          onShowAccount={() => navigate('account')}
          onLogIn={() => navigate('login')}
          onLogOut={() => {
            logOut()
              .catch(() => undefined)
              .finally(() => {
                if (siteSettings.login_required) {
                  // Nothing the account loaded is left on the page.
                  window.location.assign(addressFor('login'))
                  return
                }
                setUser(null)
                navigate('welcome')
              })
          }}
        />

        <div className={isLockedOut ? 'site-body site-body-without-nav' : 'site-body'}>
          {!isLockedOut && <SideNav groups={navGroups} activeView={activeView} isOpen={isMenuOpen} onNavigate={navigate} />}

          {/* The page content and the footer share the column to the right of the sidebar. */}
          <div className="site-column">
            {!areSettingsLoaded || !isAccountKnown ? (
              // A moment while the settings and the login are checked, so a closed site never shows its pages.
              <main className="site-main" id="content" />
            ) : isLockedOut ? (
              <main className="site-main" id="content">
                {lockedOutView === 'unsubscribe' && emailLink && <UnsubscribePage token={emailLink.token} />}
                {lockedOutView === 'messageRequest' && emailLink && <MessageRequestPage token={emailLink.token} onNavigate={navigate} />}
                {lockedOutView === 'verify' && emailLink && <VerifyEmailPage token={emailLink.token} onVerified={handleVerified} />}
                {lockedOutView === 'privacy' && <PrivacyPage onNavigate={navigate} siteTitle={siteSettings.title} />}
                {lockedOutView === 'smsTerms' && <SmsTermsPage onNavigate={navigate} siteTitle={siteSettings.title} />}
                {lockedOutView === 'postingPolicy' && <PostingPolicyPage onNavigate={navigate} siteTitle={siteSettings.title} />}
                {(lockedOutView === 'login' || lockedOutView === 'forgot' || lockedOutView === 'reset') && (
                  <AccountPage
                    key={lockedOutView}
                    mode={lockedOutView}
                    token={emailLink?.token ?? ''}
                    onDone={(loggedInUser) => setUser(loggedInUser)}
                    onNavigate={navigate}
                    isLoginRequired
                    siteTitle={siteSettings.title}
                  />
                )}
              </main>
            ) : (
            <main className="site-main" id="content">
              {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}

              {activeView === 'welcome' && (
                <WelcomePage
                siteTitle={siteSettings.title}
                  welcomeHtml={siteSettings.welcome_html}
                  translations={translations}
                  commentaries={commentaries}
                  devotionals={devotionals}
                  otherBooks={otherBooks}
                  songs={songs}
                  maps={maps}
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
                onOpenMap={openMap}
                onOpenFaq={(question) => {
                  setFaqRequest({ question, id: Date.now() })
                  navigate('faq')
                }}
              />
              {user && user.logs_in_with_phone && !user.phone_verified && <ConfirmPhoneBox user={user} onConfirmed={setUser} />}
              {user && user.email && !user.email_verified && activeView !== 'verify' && (
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
              {/* Kept mounted so a half-written post is not lost; made again for another account. */}
              <ConversationsPage key={`conversations-${user?.id ?? 'logged-out'}`} isHidden={activeView !== 'conversations'} />
              <ConversationsPage key={`prayer-${user?.id ?? 'logged-out'}`} board="prayer" isHidden={activeView !== 'prayerWall'} />
              {activeView === 'notes' && <NotesPage books={books} translation={chooseContextTranslation(translations)} onOpenItem={openNoteItem} />}
              {activeView === 'publicLists' && <PublicListsPage
                  key={`public-lists-${user?.id ?? 'logged-out'}`}
                  onOpenEntry={openListEntry}
                  onNavigate={navigate}
                  initialPlaylistId={publicPlaylistFocus}
                  onPlayPlaylist={(name, songIds) => {
                    setMusicPlayRequest({ name, songIds, key: Date.now() })
                    navigate('music')
                  }}
                />}
              {activeView === 'lists' && <MyListsPage key={`lists-${user?.id ?? 'logged-out'}`} onOpenEntry={openListEntry} onNavigate={navigate} />}
            {activeView === 'unsubscribe' && emailLink && <UnsubscribePage token={emailLink.token} />}
            {activeView === 'messageRequest' && emailLink && <MessageRequestPage token={emailLink.token} onNavigate={navigate} />}
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
              {activeView === 'help' && <HelpPage translations={translations} onNavigate={navigate} hasMusic={songs.length > 0} hasMaps={maps.length > 0} siteTitle={siteSettings.title} />}
              {activeView === 'tutorial' && <TutorialPage onNavigate={navigate} siteTitle={siteSettings.title} />}
              {activeView === 'externalSites' && <ExternalSitesPage sites={externalSites} />}
              {activeView === 'privacy' && <PrivacyPage onNavigate={navigate} siteTitle={siteSettings.title} />}
              {activeView === 'smsTerms' && <SmsTermsPage onNavigate={navigate} siteTitle={siteSettings.title} />}
              {activeView === 'postingPolicy' && <PostingPolicyPage onNavigate={navigate} siteTitle={siteSettings.title} />}
              {(activeView === 'verseOfTheDay' || activeView === 'devotionalOfTheDay') && (
                <DayCardPage
                  key={activeView}
                  kind={activeView === 'verseOfTheDay' ? 'verse' : 'devotional'}
                  onOpenVerse={openVerse}
                  onOpenReading={(devotional, section, unit) => {
                    setDestination({ id: Date.now(), kind: 'devotional', devotional, section, unit })
                    navigate('devotionals')
                  }}
                />
              )}
              {activeView === 'account' && (
                <MyAccountPage
                  key={`account-${user?.id ?? 0}`}
                  user={user}
                  isAccountKnown={isAccountKnown}
                  wasAccountClosed={wasAccountClosed}
                  onUserChanged={setUser}
                  onNavigate={navigate}
                  onAccountClosed={() => {
                    setWasAccountClosed(true)
                    setUser(null)
                  }}
                />
              )}
              {activeView === 'copyright' && (
                <CopyrightPage onBack={() => navigate('help')} devotionals={[...devotionals, ...otherBooks]} commentaries={commentaries} />
              )}

              {/* The form stays mounted too, so a half-written message is not lost. */}
              <ContactPage isHidden={activeView !== 'contact'} />
              {/* The FAQ stays mounted too, so the answers it has shown are kept. */}
              <FaqPage isHidden={activeView !== 'faq'} questionRequest={faqRequest} />

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
                  kindleBooks={kindleDevotionals}
                />
              )}
              {devotionals.length === 0 && (
                <KindleShelf books={kindleDevotionals} isHidden={activeView !== 'devotionals'} pageHeading="Read the devotionals" />
              )}
              {otherBooks.length > 0 && (
                <DevotionalsTab
                  collection="books"
                  devotionals={otherBooks}
                  translations={translations}
                  isHidden={activeView !== 'books'}
                  destination={destination?.kind === 'devotional' && isOtherBook(destination.devotional) ? destination : null}
                  kindleBooks={kindleOtherBooks}
                />
              )}
              {otherBooks.length === 0 && (
                <KindleShelf books={kindleOtherBooks} isHidden={activeView !== 'books'} pageHeading="Read other books" />
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
                  <MusicPage songs={songs} isHidden={activeView !== 'music'} focus={musicFocus} playRequest={musicPlayRequest} />
                  <MusicSearchPage
                    isHidden={activeView !== 'searchMusic'}
                    onOpen={(songId) => {
                      setMusicFocus({ id: songId, key: Date.now() })
                      navigate('music')
                    }}
                  />
                </>
              )}
              {maps.length > 0 && (
                <>
                  <MapsPage maps={maps} isHidden={activeView !== 'maps'} focus={mapFocus} onOpenVerse={openVerse} />
                  <MapSearchPage isHidden={activeView !== 'searchMaps'} onOpen={openMap} />
                </>
              )}
            </main>
            )}

            <SiteFooter copyrightText={siteSettings.copyright} />
          </div>
        </div>
      </div>
      <SiteTooltip />
    </AccountContext.Provider>
  )
}

export default App
