import { useContext, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchConversationPage } from './api'
import ConversationPostCard from './ConversationPostCard'
import ConversationPostForm from './ConversationPostForm'
import PrayerListEmailPanel from './PrayerListEmailPanel'
import MessageRequestsBox from './MessageRequestsBox'
import type { ConversationBoard, ConversationPage } from './types'

interface ConversationsPageProps {
  // Which board this page shows: Conversations, or the Prayer Wall. Each shows only its own posts.
  board?: ConversationBoard
  // The page stays mounted while another is open, so a half-written post is not lost.
  isHidden: boolean
}

// What each board calls itself; everything else about the two pages is the same.
const boardWords: Record<ConversationBoard, { heading: string; intro: string; write: string; none: string }> = {
  conversations: {
    heading: 'Conversations',
    intro: 'Posts by members of this site, newest first, with their replies. Anyone can read and search them.',
    write: 'Write a post',
    none: 'Nobody has written a post yet.',
  },
  prayer: {
    heading: 'Prayer Wall',
    intro:
      'Prayer requests and praises from members of this site, newest first, with their replies. Anyone can read and search them, and pray along. A request can be posted anonymously, or privately (seen only by its author and the site owner).',
    write: 'Share a prayer request',
    none: 'Nobody has shared a prayer request yet.',
  },
}

const postsPerPage = 10

// Conversations: posts by the site's members, newest first, each with its replies. Anyone may read and search them,
// logged in or not (the owner's choice, 2026-11-14). Only accounts an administrator allowed (use_conversations; the
// server checks too, and says so in can_post) may write posts and replies and change or delete their own.
// The page asks search engines not to index it (members' names are on it); it is not in the sitemap either.
function ConversationsPage({ board = 'conversations', isHidden }: ConversationsPageProps) {
  const words = boardWords[board]
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
  // From the server's answer, so it is right even before the account has loaded.
  const canPost = result?.can_post === true
  const userId = user?.id ?? null
  const searchWords = useMemo(() => query.split(/\s+/).filter((word) => word !== ''), [query])

  // While the page is shown, ask search engines not to index it (it shows members' names).
  useEffect(() => {
    if (isHidden) {
      return
    }
    const robots = document.createElement('meta')
    robots.name = 'robots'
    robots.content = 'noindex'
    document.head.appendChild(robots)
    return () => robots.remove()
  }, [isHidden])

  useEffect(() => {
    if (isHidden) {
      return
    }
    const controller = new AbortController()
    fetchConversationPage({ board, query, onlyMine, page, perPage: postsPerPage }, controller.signal)
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
  }, [board, isHidden, userId, query, onlyMine, page, reload])

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

  const pageCount = result ? Math.max(1, Math.ceil(result.total / postsPerPage)) : 1
  const isFiltered = query !== '' || onlyMine

  return (
    <div className="notes-page conversations-page" hidden={isHidden}>
      <h1>{words.heading}</h1>
      <p>{words.intro}</p>
      {/* Anyone with an account may get the requests by email; posting still needs an invitation. */}
      {board === 'prayer' && <PrayerListEmailPanel />}
      {result !== null && !canPost && (
        <p className="conversation-readers-note">
          Members the site has invited can write posts and reply.{' '}
          {user === null ? (
            <>
              If you are one,{' '}
              <button type="button" className="link-button" onClick={() => onNavigate('login')}>
                log in
              </button>
              ; to ask to join, use the{' '}
            </>
          ) : (
            <>To ask to join, use the </>
          )}
          <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
            Contact
          </button>{' '}
          page.
        </p>
      )}
      {/* Requests from people who would like to send this member posts (2026-11-23). */}
      {board === 'conversations' && userId !== null && (
        <MessageRequestsBox isHidden={isHidden} onAnswered={() => setReload((count) => count + 1)} />
      )}
      {canPost && (
        <>
          <p>Every member can reply to any post; only you can change or delete your own posts and replies.</p>
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
                {words.write}
              </button>
            )}
          </div>
        </>
      )}

      {/* Kept in the page while closed, so a half-written post stays and the editor is never made twice. */}
      <section className="conversation-new" hidden={!canPost || !isWriting} aria-label={words.write}>
        <h2>{words.write}</h2>
        <ConversationPostForm
          board={board}
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
          aria-label="Search the posts by title, text, author or replies"
          onChange={(event) => setSearchText(event.target.value)}
        />
        <button type="submit" className="primary-button">
          Search
        </button>
        {(query !== '' || searchText !== '') && (
          <button type="button" className="secondary-button" onClick={clearSearch}>
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
              : words.none
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
              canReply={canPost}
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
