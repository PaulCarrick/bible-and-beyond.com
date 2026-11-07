import { useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchVerseNotes, saveVerseNote } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { Note, VerseTarget } from './types'

interface NotesPanelProps {
  target: VerseTarget
  // Closes the window (used before sending the visitor to log in).
  onClose: () => void
}

function formatTime(isoTime: string) {
  return new Date(isoTime).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// Write a note on a verse, and read the notes already written on it. Notes belong to a logged-in visitor.
function NotesPanel({ target, onClose }: NotesPanelProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [savedMessage, setSavedMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const { translation, book_number: book, chapter, verse, reference } = target
  const userId = user?.id ?? null

  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchVerseNotes(book, chapter, verse, controller.signal)
      .then(setNotes)
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId, book, chapter, verse])

  function goTo(view: 'login' | 'register') {
    onClose()
    onNavigate(view)
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    const editor = editorReference.current
    if (!editor || isSaving) {
      return
    }
    setErrorMessage('')
    setSavedMessage('')
    if (editor.isEmpty()) {
      setErrorMessage('Please write something in the note.')
      return
    }
    setIsSaving(true)
    try {
      const note = await saveVerseNote(translation, book, chapter, verse, editor.getHtml())
      setNotes((current) => [note, ...(current ?? [])])
      editor.clear()
      setSavedMessage('Your note is saved.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your note could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  if (user === null) {
    return (
      <div className="notes-panel">
        <p>
          Notes are private to your account.{' '}
          <button type="button" className="link-button" onClick={() => goTo('login')}>
            Log in
          </button>{' '}
          or{' '}
          <button type="button" className="link-button" onClick={() => goTo('register')}>
            set up an account
          </button>{' '}
          to write a note on {reference}.
        </p>
      </div>
    )
  }

  return (
    <div className="notes-panel">
      <form className="contact-form" onSubmit={handleSave}>
        <span id="note-editor-label" className="visually-hidden">
          Your note on {reference}
        </span>
        <RichTextEditor ref={editorReference} placeholder={`Write a note on ${reference}`} labelledBy="note-editor-label" />
        {errorMessage && (
          <p className="error" role="alert">
            {errorMessage}
          </p>
        )}
        {savedMessage && <p role="status">{savedMessage}</p>}
        <button type="submit" className="primary-button" disabled={isSaving}>
          {isSaving ? 'Saving…' : 'Save note'}
        </button>
      </form>

      {notes !== null && notes.length > 0 && (
        <>
          <h3>Your notes on {reference}</h3>
          <ul className="note-list">
            {notes.map((note) => (
              <li key={note.id} className="note">
                <time dateTime={note.created_at}>{formatTime(note.created_at)}</time>
                {/* The server cleans the note (a short list of tags, safe links) before it keeps it. */}
                <div className="note-body" dangerouslySetInnerHTML={{ __html: note.body }} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default NotesPanel
