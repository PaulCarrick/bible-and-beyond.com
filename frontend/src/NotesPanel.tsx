import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchNotes, saveNote } from './api'
import NoteCard from './NoteCard'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { Note, NoteSubject, VerseTarget } from './types'

interface NotesPanelProps {
  target: VerseTarget
  // Closes the window (used before sending the visitor to log in).
  onClose: () => void
}

// Write a note on a verse, a commentary note or a devotional reading, and read the notes already written on it. Notes belong to a logged-in visitor.
function NotesPanel({ target, onClose }: NotesPanelProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [savedMessage, setSavedMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const { reference } = target
  // A verse unless the link said otherwise. A verse is the same in every Bible, so the Bible read is only
  // kept with the note.
  const subject: NoteSubject = useMemo(
    () =>
      target.subject ?? {
        item_type: 'bible_verse',
        source_code: target.translation,
        book_number: target.book_number,
        chapter: target.chapter,
        verse: target.verse,
      },
    [target],
  )
  const userId = user?.id ?? null

  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchNotes(subject, controller.signal)
      .then(setNotes)
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId, subject])

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
      const note = await saveNote(subject, editor.getHtml())
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
              <NoteCard
                key={note.id}
                note={note}
                showTitle={false}
                onChanged={(changed) => setNotes((current) => (current ?? []).map((entry) => (entry.id === changed.id ? changed : entry)))}
                onDeleted={(id) => setNotes((current) => (current ?? []).filter((entry) => entry.id !== id))}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default NotesPanel
