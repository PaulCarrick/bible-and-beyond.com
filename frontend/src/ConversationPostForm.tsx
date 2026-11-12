import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { saveConversationPost } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { ConversationPost } from './types'

interface ConversationPostFormProps {
  // The post being changed; none for a new post.
  post?: ConversationPost
  onSaved: (post: ConversationPost) => void
  onCancel: () => void
}

// The limits the server keeps (conversations.py).
const titleLimit = 200

// A title and the text of a post, in the editor shared with notes and the contact form.
function ConversationPostForm({ post, onSaved, onCancel }: ConversationPostFormProps) {
  const [title, setTitle] = useState(post?.title ?? '')
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
      const saved = await saveConversationPost(post?.id ?? null, title.trim(), editor.getHtml())
      if (!post) {
        setTitle('')
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
