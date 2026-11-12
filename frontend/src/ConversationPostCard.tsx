import { useMemo, useState } from 'react'
import { deleteConversationPost } from './api'
import ConversationPostForm from './ConversationPostForm'
import { highlightHtml } from './highlightHtml'
import type { ConversationPost } from './types'

interface ConversationPostCardProps {
  post: ConversationPost
  onChanged: (post: ConversationPost) => void
  onDeleted: (id: number) => void
  // The words searched for, shown highlighted in the post (none outside a search).
  highlightTerms: string[]
}

function formatTime(isoTime: string) {
  return new Date(isoTime).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// One post: its title, author, time and text, with Edit and Delete for its author. Editing happens in place;
// deleting asks first.
function ConversationPostCard({ post, onChanged, onDeleted, highlightTerms }: ConversationPostCardProps) {
  const [mode, setMode] = useState<'reading' | 'editing' | 'confirming'>('reading')
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const termsKey = highlightTerms.join('\u0000')
  const shownBody = useMemo(
    () => highlightHtml(post.body, termsKey === '' ? [] : termsKey.split('\u0000')),
    [post.body, termsKey],
  )
  const wasEdited = post.updated_at !== post.created_at

  async function handleDelete() {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    try {
      await deleteConversationPost(post.id)
      onDeleted(post.id)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The post could not be deleted.')
      setIsBusy(false)
    }
  }

  return (
    <li className="note conversation-post">
      {mode === 'editing' ? (
        <ConversationPostForm
          post={post}
          onSaved={(saved) => {
            onChanged(saved)
            setMode('reading')
          }}
          onCancel={() => setMode('reading')}
        />
      ) : (
        <>
          <h2 className="note-title">{post.title}</h2>
          <p className="conversation-byline">
            {post.author}
            {post.is_mine && ' (you)'} &middot;{' '}
            <time dateTime={post.created_at}>{formatTime(post.created_at)}</time>
            {wasEdited && ` (edited ${formatTime(post.updated_at)})`}
          </p>
          {/* The server cleans the post (a short list of tags, safe links) before it keeps it; the search words are
              only wrapped in <mark> in its text. */}
          <div className="note-body" dangerouslySetInnerHTML={{ __html: shownBody }} />
          {post.is_mine &&
            (mode === 'confirming' ? (
              <div className="note-actions" role="alert">
                <span>Delete this post?</span>
                <button type="button" className="link-button danger" disabled={isBusy} onClick={handleDelete}>
                  {isBusy ? 'Deleting…' : 'Yes, delete it'}
                </button>
                <button type="button" className="link-button" disabled={isBusy} onClick={() => setMode('reading')}>
                  No, keep it
                </button>
              </div>
            ) : (
              <div className="note-actions">
                <button type="button" className="link-button" onClick={() => setMode('editing')}>
                  Edit
                  <span className="visually-hidden"> the post {post.title}</span>
                </button>
                <button type="button" className="link-button" onClick={() => setMode('confirming')}>
                  Delete
                  <span className="visually-hidden"> the post {post.title}</span>
                </button>
              </div>
            ))}
        </>
      )}
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
    </li>
  )
}

export default ConversationPostCard
