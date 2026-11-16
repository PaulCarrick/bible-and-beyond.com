import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { saveConversationPost } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { ConversationBoard, ConversationPost } from './types'

interface ConversationPostFormProps {
  // The post being changed; none for a new post.
  post?: ConversationPost
  // The board a new post goes on (a changed post stays on its own).
  board?: ConversationBoard
  onSaved: (post: ConversationPost) => void
  onCancel: () => void
}

// The limits the server keeps (conversations.py).
const titleLimit = 200

// A title and the text of a post, in the editor shared with notes and the contact form. On the Prayer Wall it
// also has three choices, all off to start: anonymous, private, and email to the prayer list (not with private).
function ConversationPostForm({ post, board = 'conversations', onSaved, onCancel }: ConversationPostFormProps) {
  const isPrayer = (post?.board ?? board) === 'prayer'
  const [title, setTitle] = useState(post?.title ?? '')
  const [isAnonymous, setIsAnonymous] = useState(post?.is_anonymous ?? false)
  const [isPrivate, setIsPrivate] = useState(post?.is_private ?? false)
  const [emailToPrayerList, setEmailToPrayerList] = useState(post?.email_to_prayer_list ?? false)
  const [emailReplies, setEmailReplies] = useState(post?.email_replies ?? false)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const labelId = useId()

  // The editor is made when the form is; fill it with the post as it is.
  useEffect(() => {
    if (post) {
      editorReference.current?.setHtml(post.body)
    }
  }, [post])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const editor = editorReference.current
    if (!editor || isSaving) {
      return
    }
    if (title.trim() === '') {
      setErrorMessage('Please give the post a title.')
      return
    }
    if (editor.isEmpty()) {
      setErrorMessage('Please write something in the post.')
      return
    }
    setIsSaving(true)
    setErrorMessage('')
    try {
      const saved = await saveConversationPost(post?.id ?? null, title.trim(), editor.getHtml(), post?.board ?? board, {
        isAnonymous: isPrayer && isAnonymous,
        isPrivate: isPrayer && isPrivate,
        emailToPrayerList: isPrayer && emailToPrayerList && !isPrivate,
        emailReplies: !isPrayer && emailReplies,
      })
      if (!post) {
        setTitle('')
        setIsAnonymous(false)
        setIsPrivate(false)
        setEmailToPrayerList(false)
        setEmailReplies(false)
        editor.clear()
      }
      onSaved(saved)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your post could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form className="contact-form conversation-form" onSubmit={handleSubmit}>
      <label className="contact-field">
        Title
        <input type="text" value={title} maxLength={titleLimit} required onChange={(event) => setTitle(event.target.value)} />
      </label>
      <span id={labelId} className="visually-hidden">
        {post ? `The text of your post ${post.title}` : 'The text of your post'}
      </span>
      <RichTextEditor ref={editorReference} placeholder="Write your post" labelledBy={labelId} />
      {!isPrayer && (
        <div className="prayer-options">
          <label className="inline-label">
            <input type="checkbox" checked={emailReplies} onChange={(event) => setEmailReplies(event.target.checked)} />
            Email me replies
            <small>Each new reply to this post is emailed to you (to a confirmed address). Every email has a link to stop them.</small>
          </label>
        </div>
      )}
      {isPrayer && (
        <fieldset className="prayer-options">
          <legend className="visually-hidden">Who sees this request</legend>
          <label className="inline-label">
            <input type="checkbox" checked={isAnonymous} onChange={(event) => setIsAnonymous(event.target.checked)} />
            Post anonymously
            <small>Your name is not shown; it says “Anonymous”.</small>
          </label>
          <label className="inline-label">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(event) => {
                setIsPrivate(event.target.checked)
                if (event.target.checked) {
                  setEmailToPrayerList(false)
                }
              }}
            />
            Private
            <small>
              Nobody else can see it on the Prayer Wall, but <strong>the site owner and administrators can read it</strong>
              , and it is sent to them in their weekly prayer list email. It is not emailed to anyone else.
            </small>
          </label>
          <label className="inline-label">
            <input
              type="checkbox"
              checked={emailToPrayerList && !isPrivate}
              disabled={isPrivate}
              onChange={(event) => setEmailToPrayerList(event.target.checked)}
            />
            Email this request to the prayer list
            <small>It goes in the next weekly email to everyone who signed up for the prayer list.</small>
          </label>
        </fieldset>
      )}
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      <div className="note-actions">
        <button type="submit" className="primary-button" disabled={isSaving}>
          {isSaving ? 'Saving…' : post ? 'Save changes' : 'Post it'}
        </button>
        <button type="button" className="secondary-button" disabled={isSaving} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export default ConversationPostForm
