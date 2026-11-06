import { useEffect, useState } from 'react'
import { fetchBooks, fetchCommentarySources, fetchDevotionals, fetchTranslations } from './api'
import BibleTab from './BibleTab'
import BrowseTab from './BrowseTab'
import CopyrightPage from './CopyrightPage'
import DevotionalsTab from './DevotionalsTab'
import SearchTab from './SearchTab'
import SideNav from './SideNav'
import type { NavGroup } from './SideNav'
import SiteFooter from './SiteFooter'
import SiteHeader from './SiteHeader'
import WelcomePage from './WelcomePage'
import type { Book, CommentarySource, DevotionalInfo, Translation } from './types'
import type { View } from './views'
import './App.css'

function App() {
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [devotionals, setDevotionals] = useState<DevotionalInfo[]>([])
  const [loadErrorMessage, setLoadErrorMessage] = useState('')
  const [activeView, setActiveView] = useState<View>('welcome')
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
  ]

  return (
    <div className="app-shell">
      <SiteHeader isMenuOpen={isMenuOpen} onToggleMenu={() => setIsMenuOpen(!isMenuOpen)} onGoHome={() => navigate('welcome')} />

      <div className="site-body">
        <SideNav groups={navGroups} activeView={activeView} isOpen={isMenuOpen} onNavigate={navigate} />

        {/* The page content and the footer share the column to the right of the sidebar. */}
        <div className="site-column">
          <main className="site-main" id="content">
            {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}

            {activeView === 'welcome' && (
              <WelcomePage
                translations={translations}
                commentaries={commentaries}
                devotionals={devotionals}
                onNavigate={navigate}
              />
            )}
            {activeView === 'copyright' && (
              <CopyrightPage onBack={() => navigate('welcome')} devotionals={devotionals} />
            )}

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

          <SiteFooter onShowCopyrightNotices={() => navigate('copyright')} />
        </div>
      </div>
    </div>
  )
}

export default App
