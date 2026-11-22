import { useContext, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { AccountContext } from './AccountContext'
import { fetchMyGroups, saveConversationPost } from './api'
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

// The Prayer Wall's one choice of who sees a request (the owner's request, 2026-11-16, in place of three
// checkboxes): Public, Post anonymously, Private, Add to the prayer list email, and, for each group the member is
// in, "Email <group>" and "Email <group> leader" (sent at once; the request becomes private).
type Sharing = 'public' | 'anonymous' | 'private' | 'prayer_list' | `group:${number}` | `leader:${number}`

function sharingOf(post?: ConversationPost): Sharing {
  if (post?.share_with && post.share_group_id) {
    return `${post.share_with}:${post.share_group_id}`
  }
  if (post?.is_private) {
    return 'private'
  }
  if (post?.email_to_prayer_list) {
    return 'prayer_list'
  }
  return post?.is_anonymous ? 'anonymous' : 'public'
}

// A title and the text of a post, in the editor shared with notes and the contact form. On the Prayer Wall it
// also has the choice of who sees it (Sharing), Public to start.
function ConversationPostForm({ post, board = 'conversations', onSaved, onCancel }: ConversationPostFormProps) {
  const isPrayer = (post?.board ?? board) === 'prayer'
  const hasEmail = Boolean(useContext(AccountContext).user?.email)
  const [title, setTitle] = useState(post?.title ?? '')
  const [sharing, setSharing] = useState<Sharing>(sharingOf(post))
  // The groups the member is in, for the "Email <group>" choices (empty when in none).
  const [groups, setGroups] = useState<{ id: number; name: string }[]>([])
  const [emailReplies, setEmailReplies] = useState(post?.email_replies ?? false)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const labelId = useId()

  useEffect(() => {
    if (!isPrayer) {
      return
    }
    const controller = new AbortController()
    fetchMyGroups(controller.signal)
      .then(setGroups)
      .catch(() => setGroups([]))
    return () => controller.abort()
  }, [isPrayer])

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
      const [kind, groupId] = sharing.split(':')
      const sharesWithGroup = isPrayer && (kind === 'group' || kind === 'leader')
      const saved = await saveConversationPost(post?.id ?? null, title.trim(), editor.getHtml(), post?.board ?? board, {
        isAnonymous: isPrayer && sharing === 'anonymous',
        isPrivate: isPrayer && (sharing === 'private' || sharesWithGroup),
        emailToPrayerList: isPrayer && sharing === 'prayer_list',
        emailReplies: !isPrayer && emailReplies,
        shareWith: sharesWithGroup ? (kind as 'group' | 'leader') : null,
        shareGroupId: sharesWithGroup ? Number(groupId) : null,
      })
      if (!post) {
        setTitle('')
        setSharing('public')
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
      {/* Email me replies: not for an account with no email address (it logs in with its phone, 2026-11-17). */}
      {!isPrayer && hasEmail && (
        <div className="prayer-options">
          <label className="inline-label">
            <input type="checkbox" checked={emailReplies} onChange={(event) => setEmailReplies(event.target.checked)} />
            Email me replies
            <small>Each new reply to this post is emailed to you (to a confirmed address). Every email has a link to stop them.</small>
          </label>
        </div>
      )}
      {isPrayer && (
        <div className="prayer-options">
          <label className="contact-field">
            Who sees this request
            <select value={sharing} onChange={(event) => setSharing(event.target.value as Sharing)}>
              <option value="public">Public</option>
              <option value="anonymous">Post anonymously</option>
              <option value="private">Private</option>
              <option value="prayer_list">Add to the prayer list email</option>
              {groups.map((group) => [
                <option key={`group-${group.id}`} value={`group:${group.id}`}>
                  Email {group.name}
                </option>,
                <option key={`leader-${group.id}`} value={`leader:${group.id}`}>
                  Email {group.name} leader
                </option>,
              ])}
            </select>
          </label>
          <small className="prayer-sharing-note">{sharingNote(sharing, groups)}</small>
        </div>
      )}
      {/* The rule (the owner's words, 2026-11-22); "Check posts with AI" on Site settings enforces it. */}
      <p className="posting-rules">
        {isPrayer ? 'Requests' : 'Posts'} should not contain profanity, political messages or ads. By posting, you agree to our{' '}
        <a href="/posting-policy" target="_blank" rel="noopener">Posting policy</a>.
      </p>
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

// What each choice means, under the list.
function sharingNote(sharing: Sharing, groups: { id: number; name: string }[]): ReactNode {
  const [kind, groupId] = sharing.split(':')
  const groupName = groups.find((group) => group.id === Number(groupId))?.name ?? 'the group'
  switch (kind) {
    case 'anonymous':
      return 'Everyone can read it, but your name is not shown; it says “Anonymous”.'
    case 'private':
      return (
        <>
          Nobody else can see it on the Prayer Wall, but <strong>the site owner and administrators can read it</strong>,
          and it is sent to them in their weekly prayer list email. It is not emailed to anyone else.
        </>
      )
    case 'prayer_list':
      return 'Everyone can read it, and it goes in the next weekly email to everyone who signed up for the prayer list.'
    case 'group':
      return `Emailed now to everyone in ${groupName}, with your name; replies come to your email address. It is private on the Prayer Wall (the site owner and administrators can read it).`
    case 'leader':
      return `Emailed now to the leader of ${groupName} only, with your name; replies come to your email address. It is private on the Prayer Wall (the site owner and administrators can read it).`
    default:
      return 'Everyone can read it on the Prayer Wall, with your name.'
  }
}

export default ConversationPostForm
