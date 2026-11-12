import { useEffect, useId, useRef, useState } from 'react'
import { saveConversationReply } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { ConversationReply } from './types'

interface ConversationReplyFormProps {
  postId: number
  // Used to name the editor for people who cannot see it.
  postTitle: string
  // The reply being changed; none for a new reply.
  reply?: ConversationReply
  onSaved: (reply: ConversationReply) => void
  onCancel: () => void
}

// The text of a reply, in the editor shared with notes and posts. A plain container with a Save button, not a
// form, so it can sit inside the post it answers.
function ConversationReplyForm({ postId, postTitle, reply, onSaved, onCancel }: ConversationReplyFormProps) {
  const [errorMessage, setErrorMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const labelId = useId()

  // The editor is made with the form; fill it with the reply as it is.
  useEffect(() => {
    if (reply) {
      editorReference.current?.setHtml(reply.body)
    }
  }, [reply])

  async function handleSave() {
    const editor = editorReference.current
    if (!editor || isSaving) {
      return
    }
    if (editor.isEmpty()) {
      setErrorMessage('Please write something in the reply.')
      return
    }
    setIsSaving(true)
    setErrorMessage('')
    try {
      const saved = await saveConversationReply(postId, reply?.id ?? null, editor.getHtml())
      if (!reply) {
        editor.clear()
      }
      onSaved(saved)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your reply could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="contact-form conversation-reply-form">
      <span id={labelId} className="visually-hidden">
        {reply ? `Edit your reply to ${postTitle}` : `Your reply to ${postTitle}`}
      </span>
      <RichTextEditor ref={editorReference} placeholder="Write your reply" labelledBy={labelId} />
      {errorMessage && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      <div className="note-actions">
        <button type="button" className="primary-button" disabled={isSaving} onClick={handleSave}>
          {isSaving ? 'Saving…' : reply ? 'Save changes' : 'Post reply'}
        </button>
        <button type="button" className="secondary-button" disabled={isSaving} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

export default ConversationReplyForm
