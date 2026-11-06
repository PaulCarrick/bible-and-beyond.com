import { useEffect, useState } from 'react'
import { fetchBooks, fetchCommentarySources, fetchTranslations } from './api'
import BibleTab from './BibleTab'
import BrowseTab from './BrowseTab'
import CopyrightPage from './CopyrightPage'
import SearchTab from './SearchTab'
import type { SearchMode } from './SearchTab'
import type { Book, CommentarySource, Translation } from './types'
import './App.css'

type TabMode = SearchMode | 'read' | 'browse'

const tabs: { mode: TabMode; label: string }[] = [
  { mode: 'read', label: 'Read the Bible' },
  { mode: 'bible', label: 'Search for specific words or phrases' },
  { mode: 'commentary', label: 'Search the commentaries' },
  { mode: 'browse', label: 'Browse the commentaries' },
]

function App() {
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [loadErrorMessage, setLoadErrorMessage] = useState('')
  const [activeMode, setActiveMode] = useState<TabMode>('read')
  const [isShowingCopyrights, setIsShowingCopyrights] = useState(false)

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

  // The commentary tab only appears once there are commentaries to search.
  const visibleTabs = tabs.filter(
    (tab) => tab.mode === 'read' || tab.mode === 'bible' || commentaries.length > 0,
  )
  const searchTabs = visibleTabs.filter(
    (tab): tab is { mode: SearchMode; label: string } => tab.mode === 'bible' || tab.mode === 'commentary',
  )

  return (
    <main className="app">
      <img className="site-logo" src="/logo.svg" alt="Bible and Beyond" />
      <nav className="tabs" aria-label="Sections">
        {visibleTabs.map((tab) => (
          <button
            type="button"
            key={tab.mode}
            className={tab.mode === activeMode ? 'tab active' : 'tab'}
            aria-current={tab.mode === activeMode ? 'page' : undefined}
            onClick={() => {
              setActiveMode(tab.mode)
              setIsShowingCopyrights(false)
              window.scrollTo(0, 0)
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}
      {isShowingCopyrights && <CopyrightPage onBack={() => setIsShowingCopyrights(false)} />}
      <BibleTab translations={translations} isHidden={isShowingCopyrights || activeMode !== 'read'} />

      {searchTabs.map((tab) => (
        <SearchTab
          key={tab.mode}
          mode={tab.mode}
          translations={translations}
          books={books}
          commentaries={commentaries}
          isHidden={isShowingCopyrights || tab.mode !== activeMode}
          onShowCopyrights={() => setIsShowingCopyrights(true)}
        />
      ))}
      {commentaries.length > 0 && (
        <BrowseTab
          commentaries={commentaries}
          translations={translations}
          isHidden={isShowingCopyrights || activeMode !== 'browse'}
        />
      )}

      <footer className="site-footer">
        Scripture for the NIV, NASB and The Message is provided through{' '}
        <a href="https://api.bible" target="_blank" rel="noreferrer">
          API.Bible
        </a>
        .{' '}
        <button type="button" className="link-button" onClick={() => setIsShowingCopyrights(true)}>
          Bible copyright notices
        </button>
      </footer>
    </main>
  )
}

export default App
