import { useMemo, useState } from 'react'
import { deleteConversationPost, setConversationAnswered } from './api'
import ConversationPostForm from './ConversationPostForm'
import ConversationReplyForm from './ConversationReplyForm'
import ConversationReplyItem from './ConversationReplyItem'
import { highlightHtml } from './highlightHtml'
import type { ConversationPost } from './types'

interface ConversationPostCardProps {
  post: ConversationPost
  onChanged: (post: ConversationPost) => void
  onDeleted: (id: number) => void
  // The words searched for, shown highlighted in the post (none outside a search).
  highlightTerms: string[]
  // Whether the visitor may reply (a member allowed Conversations); readers see no Reply button.
  canReply: boolean
}

function formatTime(isoTime: string) {
  return new Date(isoTime).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// One post: its title, author, time and text, with Edit and Delete for its author, then its replies and a Reply
// button for any member. Editing happens in place; deleting asks first. A Prayer Wall request also has an Answered
// checkbox for its author (saved at once, without editing) and an "Answered" mark for everyone once ticked.
function ConversationPostCard({ post, onChanged, onDeleted, highlightTerms, canReply }: ConversationPostCardProps) {
  const [mode, setMode] = useState<'reading' | 'editing' | 'confirming'>('reading')
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [isReplying, setIsReplying] = useState(false)
  const termsKey = highlightTerms.join('\u0000')
  const shownBody = useMemo(
    () => highlightHtml(post.body, termsKey === '' ? [] : termsKey.split('\u0000')),
    [post.body, termsKey],
  )
  const wasEdited = post.updated_at !== post.created_at
  const isPrayer = post.board === 'prayer'

  async function handleAnswered(answered: boolean) {
    if (isBusy) {
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    try {
      onChanged(await setConversationAnswered(post.id, answered))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'That could not be saved.')
    } finally {
      setIsBusy(false)
    }
  }

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
          <h2 className="note-title">
            {post.title}
            {post.answered_at && (
              <span className="prayer-answered-mark" title={`Marked answered ${formatTime(post.answered_at)}`}>
                Answered
              </span>
            )}
          </h2>
          <p className="conversation-byline">
            {post.author}
            {post.is_mine && ' (you)'} &middot;{' '}
            <time dateTime={post.created_at}>{formatTime(post.created_at)}</time>
            {wasEdited && ` (edited ${formatTime(post.updated_at)})`}
          </p>
          {/* A post to one member (2026-11-23): only the two of them see it; its author also sees whether it has been
              accepted. */}
          {post.recipient && (
            <p className="prayer-post-options conversation-direct">
              {post.is_mine
                ? `Private: to ${post.recipient.name} only${
                    post.delivery === 'pending'
                      ? ' · waiting for them to accept posts from you'
                      : post.delivery === 'declined'
                        ? ' · not delivered: they are not accepting posts from you'
                        : ''
                  }`
                : 'Private: sent to you only'}
            </p>
          )}
          {/* Only the author's own posts say how they were shared (others see "Anonymous" and never a private post). */}
          {post.is_mine && (post.is_anonymous || post.is_private || post.email_to_prayer_list || post.email_replies) && (
            <p className="prayer-post-options">
              {[
                post.share_with &&
                  `Emailed ${post.shared_at ? '' : '(on its way) '}to ${post.share_group_name ?? 'a group'}${post.share_with === 'leader' ? ' leader' : ''}`,
                post.is_private && 'Private: only you and the site owner and administrators can see it',
                post.is_anonymous && 'Posted anonymously',
                post.email_to_prayer_list && 'Emailed to the prayer list',
                post.email_replies && 'Replies are emailed to you',
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
          {/* The server cleans the post (a short list of tags, safe links) before it keeps it; the search words are
              only wrapped in <mark> in its text. */}
          <div className="note-body" dangerouslySetInnerHTML={{ __html: shownBody }} />
          {mode === 'confirming' ? (
            <div className="note-actions conversation-actions" role="alert">
              <span>Delete this post?</span>
              <button type="button" className="secondary-button small-button danger-button" disabled={isBusy} onClick={handleDelete}>
                {isBusy ? 'Deleting…' : 'Yes, delete it'}
              </button>
              <button type="button" className="secondary-button small-button" disabled={isBusy} onClick={() => setMode('reading')}>
                No, keep it
              </button>
            </div>
          ) : (post.is_mine || canReply) && (
            // One line under the post: Edit and Delete for its author, and Reply for every member (none for a reader).
            <div className="note-actions conversation-actions">
              {post.is_mine && isPrayer && (
                <label className="inline-label prayer-answered-box">
                  <input
                    type="checkbox"
                    checked={post.answered_at !== null}
                    disabled={isBusy}
                    onChange={(event) => handleAnswered(event.target.checked)}
                  />
                  Answered
                  <span className="visually-hidden"> (the request {post.title})</span>
                </label>
              )}
              {post.is_mine && (
                <>
                  <button type="button" className="secondary-button small-button" onClick={() => setMode('editing')}>
                    Edit
                    <span className="visually-hidden"> the post {post.title}</span>
                  </button>
                  <button type="button" className="secondary-button small-button" onClick={() => setMode('confirming')}>
                    Delete
                    <span className="visually-hidden"> the post {post.title}</span>
                  </button>
                </>
              )}
              {canReply && !isReplying && (
                <button type="button" className="secondary-button small-button" onClick={() => setIsReplying(true)}>
                  Reply
                  <span className="visually-hidden"> to {post.title}</span>
                </button>
              )}
            </div>
          )}
        </>
      )}
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}

      {/* The indented replies, shown only when there are some or one is being written. */}
      {(post.replies.length > 0 || isReplying) && (
        <section className="conversation-replies" aria-label={`Replies to ${post.title}`}>
          {post.replies.length > 0 && (
            <>
              <h3 className="conversation-replies-heading">
                {post.replies.length === 1 ? '1 reply' : `${post.replies.length} replies`}
              </h3>
              <ul className="conversation-reply-list">
                {post.replies.map((reply) => (
                  <ConversationReplyItem
                    key={reply.id}
                    reply={reply}
                    postTitle={post.title}
                    highlightTerms={highlightTerms}
                    onChanged={(changed) =>
                      onChanged({ ...post, replies: post.replies.map((entry) => (entry.id === changed.id ? changed : entry)) })
                    }
                    onDeleted={(id) => onChanged({ ...post, replies: post.replies.filter((entry) => entry.id !== id) })}
                  />
                ))}
              </ul>
            </>
          )}
          {isReplying && (
            <ConversationReplyForm
              postId={post.id}
              postTitle={post.title}
              onSaved={(reply) => {
                onChanged({ ...post, replies: [...post.replies, reply] })
                setIsReplying(false)
              }}
              onCancel={() => setIsReplying(false)}
            />
          )}
        </section>
      )}
    </li>
  )
}

export default ConversationPostCard
