import { useCallback, useEffect, useState } from 'react'
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
import AccountPage from './AccountPage'
import VerifyEmailPage from './VerifyEmailPage'
import ContactPage from './ContactPage'
import CopyrightPage from './CopyrightPage'
import DevotionalsTab from './DevotionalsTab'
import SearchTab from './SearchTab'
import SideNav from './SideNav'
import type { NavGroup } from './SideNav'
import SiteFooter from './SiteFooter'
import SiteHeader from './SiteHeader'
import WelcomePage from './WelcomePage'
import type { Book, CommentarySource, DevotionalInfo, SiteSettings, Translation } from './types'
import type { AccountUser } from './types'
import type { View } from './views'
import './App.css'

// What the pages show until the administrator's settings arrive, and if they cannot be had.
const defaultSiteSettings: SiteSettings = {
  title: 'Bible and Beyond',
  copyright: 'Copyright © 2026 by Paul Carrick. All Rights Reserved.',
}

// The links in our emails open the site with ?verify=... or ?reset=... on the end.
function readEmailLink(): { kind: 'verify' | 'reset'; token: string } | null {
  const parameters = new URLSearchParams(window.location.search)
  const verifyToken = parameters.get('verify')
  const resetToken = parameters.get('reset')
  if (verifyToken) {
    return { kind: 'verify', token: verifyToken }
  }
  return resetToken ? { kind: 'reset', token: resetToken } : null
}

function App() {
  const [emailLink] = useState(readEmailLink)
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [devotionals, setDevotionals] = useState<DevotionalInfo[]>([])
  const [siteSettings, setSiteSettings] = useState<SiteSettings>(defaultSiteSettings)
  const [user, setUser] = useState<AccountUser | null>(null)
  const [resendMessage, setResendMessage] = useState('')
  const [loadErrorMessage, setLoadErrorMessage] = useState('')
  const [activeView, setActiveView] = useState<View>(emailLink?.kind ?? 'welcome')
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

  // The token is kept in the page; it is taken out of the address so it is not bookmarked or shared by mistake.
  useEffect(() => {
    if (emailLink) {
      window.history.replaceState(null, '', window.location.pathname)
    }
  }, [emailLink])

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

  function navigate(view: View) {
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
              { view: 'commentary' as View, label: 'Search the commentaries' },
              { view: 'browse' as View, label: 'Browse the commentaries' },
            ],
          },
        ]
      : []),
    ...(devotionals.length > 0
      ? [{ heading: 'Devotionals', entries: [{ view: 'devotionals' as View, label: 'Read the devotionals' }] }]
      : []),
    { heading: 'About', entries: [{ view: 'contact' as View, label: 'Contact' }] },
  ]

  return (
    <div className="app-shell">
      <SiteHeader
        title={siteSettings.title}
        isMenuOpen={isMenuOpen}
        onToggleMenu={() => setIsMenuOpen(!isMenuOpen)}
        onGoHome={() => navigate('welcome')}
        user={user}
        onSetUpAccount={() => navigate('register')}
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
            {activeView === 'copyright' && (
              <CopyrightPage onBack={() => navigate('welcome')} devotionals={devotionals} />
            )}

            {/* The form stays mounted too, so a half-written message is not lost. */}
            <ContactPage isHidden={activeView !== 'contact'} />

            {/* The readers and searches stay mounted while another page is open, so nothing is lost. */}
            <BibleTab translations={translations} isHidden={activeView !== 'read'} />
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
                <BrowseTab commentaries={commentaries} translations={translations} isHidden={activeView !== 'browse'} />
              </>
            )}
            {devotionals.length > 0 && (
              <DevotionalsTab devotionals={devotionals} translations={translations} isHidden={activeView !== 'devotionals'} />
            )}
          </main>

          <SiteFooter copyrightText={siteSettings.copyright} onShowCopyrightNotices={() => navigate('copyright')} />
        </div>
      </div>
    </div>
  )
}

export default App
