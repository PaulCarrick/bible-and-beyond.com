import { useContext, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchConversationPage } from './api'
import ConversationPostCard from './ConversationPostCard'
import ConversationPostForm from './ConversationPostForm'
import type { ConversationPage } from './types'

interface ConversationsPageProps {
  // The page stays mounted while another is open, so a half-written post is not lost.
  isHidden: boolean
}

const postsPerPage = 10

// Conversations: posts by the site's members, newest first, for accounts an administrator allowed them
// (use_conversations; the server checks too). Every allowed member reads every post; a member can add posts and
// change or delete their own, and search them all.
function ConversationsPage({ isHidden }: ConversationsPageProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const [result, setResult] = useState<ConversationPage | null>(null)
  // What is typed in the search box, and what the list is actually searched for (set when it is submitted).
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [onlyMine, setOnlyMine] = useState(false)
  const [page, setPage] = useState(1)
  // Changed to ask for the list again (after a post is added or deleted).
  const [reload, setReload] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [isWriting, setIsWriting] = useState(false)
  const isAllowed = user?.use_conversations === true
  const userId = user?.id ?? null
  const searchWords = useMemo(() => query.split(/\s+/).filter((word) => word !== ''), [query])

  useEffect(() => {
    if (isHidden || !isAllowed) {
      return
    }
    const controller = new AbortController()
    fetchConversationPage({ query, onlyMine, page, perPage: postsPerPage }, controller.signal)
      .then((loaded) => {
        // Deleting the last post of the last page leaves that page empty: show the one before.
        if (loaded.posts.length === 0 && loaded.total > 0 && page > 1) {
          setPage(Math.ceil(loaded.total / postsPerPage))
        } else {
          setErrorMessage('')
          setResult(loaded)
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [isHidden, isAllowed, userId, query, onlyMine, page, reload])

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    setQuery(searchText.trim())
    setPage(1)
  }

  function clearSearch() {
    setSearchText('')
    setQuery('')
    setPage(1)
  }

  if (!isAllowed) {
    return (
      <div className="notes-page" hidden={isHidden}>
        <h1>Conversations</h1>
        {user === null ? (
          <p>
            Conversations are posts written by members of this site.{' '}
            <button type="button" className="link-button" onClick={() => onNavigate('login')}>
              Log in
            </button>{' '}
            to read and write them.
          </p>
        ) : (
          <p>
            Conversations are open to members the site&rsquo;s administrator has invited. To ask to join, use the{' '}
            <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
              Contact
            </button>{' '}
            page.
          </p>
        )}
      </div>
    )
  }

  const pageCount = result ? Math.max(1, Math.ceil(result.total / postsPerPage)) : 1
  const isFiltered = query !== '' || onlyMine

  return (
    <div className="notes-page conversations-page" hidden={isHidden}>
      <h1>Conversations</h1>
      <p>
        Posts by members of this site, newest first. Every member who can use Conversations can read every post; only
        you can change or delete yours.
      </p>

      <div className="notes-toolbar">
        <label className="inline-label">
          <input
            type="checkbox"
            checked={onlyMine}
            onChange={(event) => {
              setOnlyMine(event.target.checked)
              setPage(1)
            }}
          />
          Only my posts
        </label>
        {!isWriting && (
          <button type="button" className="primary-button" onClick={() => setIsWriting(true)}>
            Write a post
          </button>
        )}
      </div>

      {/* Kept in the page while closed, so a half-written post stays and the editor is never made twice. */}
      <section className="conversation-new" hidden={!isWriting} aria-label="Write a post">
        <h2>Write a post</h2>
        <ConversationPostForm
          onSaved={() => {
            // The new post is the newest: show the list from its start, without a search that hides it.
            setSearchText('')
            setQuery('')
            setPage(1)
            setReload((count) => count + 1)
            setIsWriting(false)
          }}
          onCancel={() => setIsWriting(false)}
        />
      </section>

      <form className="notes-search" role="search" onSubmit={handleSearch}>
        <input
          type="search"
          value={searchText}
          maxLength={200}
          placeholder="Search the posts"
          aria-label="Search the posts by title, text or author"
          onChange={(event) => setSearchText(event.target.value)}
        />
        <button type="submit" className="primary-button">
          Search
        </button>
        {(query !== '' || searchText !== '') && (
          <button type="button" className="link-button" onClick={clearSearch}>
            Clear search
          </button>
        )}
      </form>

      {errorMessage && <p className="error">{errorMessage}</p>}
      {result === null && !errorMessage && <p>Loading…</p>}
      {result !== null && (
        <p className="notes-count" role="status">
          {result.total === 0
            ? isFiltered
              ? 'No posts match.'
              : 'Nobody has written a post yet.'
            : `${result.total} ${result.total === 1 ? 'post' : 'posts'}${isFiltered ? (result.total === 1 ? ' matches' : ' match') : ''}${
                query !== '' ? ` “${query}”` : ''
              }.`}
        </p>
      )}
      {result !== null && result.posts.length > 0 && (
        <ul className="note-list">
          {result.posts.map((post) => (
            <ConversationPostCard
              key={post.id}
              post={post}
              highlightTerms={searchWords}
              onChanged={(changed) =>
                setResult((current) =>
                  current ? { ...current, posts: current.posts.map((entry) => (entry.id === changed.id ? changed : entry)) } : current,
                )
              }
              onDeleted={() => setReload((count) => count + 1)}
            />
          ))}
        </ul>
      )}

      {result !== null && pageCount > 1 && (
        <nav className="pagination" aria-label="Pages of posts">
          <button type="button" disabled={page <= 1} onClick={() => setPage(1)}>
            First
          </button>
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {pageCount}
          </span>
          <button type="button" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
            Next
          </button>
          <button type="button" disabled={page >= pageCount} onClick={() => setPage(pageCount)}>
            Last
          </button>
        </nav>
      )}
    </div>
  )
}

export default ConversationsPage
