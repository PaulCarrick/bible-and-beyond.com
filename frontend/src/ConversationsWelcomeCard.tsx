import { useEffect, useState } from 'react'
import { fetchConversationPage } from './api'
import type { ConversationPost } from './types'
import type { View } from './views'

interface ConversationsWelcomeCardProps {
  onNavigate: (view: View) => void
}

// The most of a first paragraph the card shows before cutting it off with "…".
const excerptLength = 300

// The first paragraph of a post as plain text (the first block of the cleaned HTML that has any text), cut at a
// word if it is long. Plain text, so nothing from the post is drawn as HTML on the welcome page.
function firstParagraph(html: string): string {
  const document = new DOMParser().parseFromString(html, 'text/html')
  const blocks = Array.from(document.body.children)
  const text = (blocks.map((block) => block.textContent?.trim() ?? '').find((blockText) => blockText !== '') ?? document.body.textContent ?? '')
    .replace(/\s+/g, ' ')
    .trim()
  if (text.length <= excerptLength) {
    return text
  }
  const cut = text.slice(0, excerptLength)
  // Cut at the last space, and drop a stop or comma left at the end, so it reads "…God…" and not "God.…".
  return `${cut
    .slice(0, Math.max(cut.lastIndexOf(' '), excerptLength / 2))
    .trimEnd()
    .replace(/[.,;:!?]+$/, '')}…`
}

function formatDate(isoTime: string) {
  return new Date(isoTime).toLocaleDateString(undefined, { dateStyle: 'medium' })
}

// The Conversations card at the foot of the welcome page, for every visitor (anyone may read): what it is, and the
// start of the latest post (its title, author, date and first paragraph) when there is one.
function ConversationsWelcomeCard({ onNavigate }: ConversationsWelcomeCardProps) {
  const [latest, setLatest] = useState<ConversationPost | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchConversationPage({ query: '', onlyMine: false, page: 1, perPage: 1 }, controller.signal)
      .then((loaded) => setLatest(loaded.posts[0] ?? null))
      // The card still works without the latest post; nothing to show if it cannot be loaded.
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  return (
    <section className="welcome-card welcome-conversations">
      <h3>Conversations</h3>
      <p>Read and search what members of this site have written. Members the site has invited can write posts and reply.</p>
      {latest && (
        <div className="welcome-latest-post">
          <p className="welcome-latest-label">Latest post</p>
          <p className="welcome-latest-title">{latest.title}</p>
          <p className="conversation-byline">
            {latest.author} &middot; <time dateTime={latest.created_at}>{formatDate(latest.created_at)}</time>
          </p>
          <p className="welcome-latest-text">{firstParagraph(latest.body)}</p>
        </div>
      )}
      <div className="welcome-buttons">
        <button type="button" className="primary-button" onClick={() => onNavigate('conversations')}>
          {latest ? 'Read the conversations' : 'Conversations'}
        </button>
      </div>
    </section>
  )
}

export default ConversationsWelcomeCard
