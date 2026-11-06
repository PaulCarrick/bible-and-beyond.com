import { useEffect, useState } from 'react'
import { fetchBooks, fetchCommentarySources, fetchTranslations } from './api'
import CopyrightPage from './CopyrightPage'
import SearchTab from './SearchTab'
import type { SearchMode } from './SearchTab'
import type { Book, CommentarySource, Translation } from './types'
import './App.css'

const tabs: { mode: SearchMode; label: string }[] = [
  { mode: 'bible', label: 'Search for specific words or phrases' },
  { mode: 'commentary', label: 'Search the commentaries' },
]

function App() {
  const [translations, setTranslations] = useState<Translation[]>([])
  const [books, setBooks] = useState<Book[]>([])
  const [commentaries, setCommentaries] = useState<CommentarySource[]>([])
  const [loadErrorMessage, setLoadErrorMessage] = useState('')
  const [activeMode, setActiveMode] = useState<SearchMode>('bible')
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
  const visibleTabs = tabs.filter((tab) => tab.mode === 'bible' || commentaries.length > 0)

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
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {loadErrorMessage && <p className="error">{loadErrorMessage}</p>}
      {isShowingCopyrights && <CopyrightPage onBack={() => setIsShowingCopyrights(false)} />}
      {visibleTabs.map((tab) => (
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
