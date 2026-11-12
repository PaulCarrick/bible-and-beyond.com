import { useMemo, useState } from 'react'
import { deleteConversationReply } from './api'
import ConversationReplyForm from './ConversationReplyForm'
import { highlightHtml } from './highlightHtml'
import type { ConversationReply } from './types'

interface ConversationReplyItemProps {
  reply: ConversationReply
  postTitle: string
  onChanged: (reply: ConversationReply) => void
  onDeleted: (id: number) => void
  // The words searched for, shown highlighted (none outside a search).
  highlightTerms: string[]
}

function formatTime(isoTime: string) {
  return new Date(isoTime).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// One reply under a post: its author, time and text, with Edit and Delete for its author.
function ConversationReplyItem({ reply, postTitle, onChanged, onDeleted, highlightTerms }: ConversationReplyItemProps) {
  const [mode, setMode] = useState<'reading' | 'editing' | 'confirming'>('reading')
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const termsKey = highlightTerms.join('\u0000')
  const shownBody = useMemo(
    () => highlightHtml(reply.body, termsKey === '' ? [] : termsKey.split('\u0000')),
    [reply.body, termsKey],
  )
  const wasEdited = reply.updated_at !== reply.created_at

  async function handleDelete() {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    try {
      await deleteConversationReply(reply.id)
      onDeleted(reply.id)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The reply could not be deleted.')
      setIsBusy(false)
    }
  }

  return (
    <li className="conversation-reply">
      <p className="conversation-byline">
        {reply.author}
        {reply.is_mine && ' (you)'} &middot; <time dateTime={reply.created_at}>{formatTime(reply.created_at)}</time>
        {wasEdited && ` (edited ${formatTime(reply.updated_at)})`}
      </p>
      {mode === 'editing' ? (
        <ConversationReplyForm
          postId={reply.post_id}
          postTitle={postTitle}
          reply={reply}
          onSaved={(saved) => {
            onChanged(saved)
            setMode('reading')
          }}
          onCancel={() => setMode('reading')}
        />
      ) : (
        <>
          {/* Cleaned by the server before it is kept; the search words are only wrapped in <mark> in its text. */}
          <div className="note-body" dangerouslySetInnerHTML={{ __html: shownBody }} />
          {reply.is_mine &&
            (mode === 'confirming' ? (
              <div className="note-actions" role="alert">
                <span>Delete this reply?</span>
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
                  <span className="visually-hidden"> your reply</span>
                </button>
                <button type="button" className="link-button" onClick={() => setMode('confirming')}>
                  Delete
                  <span className="visually-hidden"> your reply</span>
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

export default ConversationReplyItem
