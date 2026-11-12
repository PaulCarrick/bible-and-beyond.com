import { useEffect, useMemo, useRef, useState } from 'react'
import { deleteNote, updateNote } from './api'
import { highlightHtml } from './highlightHtml'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { Note } from './types'

interface NoteCardProps {
  note: Note
  // The title (what the note is about) is shown on the My notes page, where it is not already known.
  showTitle: boolean
  onChanged: (note: Note) => void
  onDeleted: (id: number) => void
  // On the My notes page: open the verse, commentary note or reading the note is about.
  onOpenItem?: (note: Note) => void
  // The words searched for, shown highlighted in the note (none outside a search).
  highlightTerms?: string[]
}

function formatTime(isoTime: string) {
  return new Date(isoTime).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// One note, with Edit and Delete. Editing happens in place; deleting asks first.
function NoteCard({ note, showTitle, onChanged, onDeleted, onOpenItem, highlightTerms = [] }: NoteCardProps) {
  const [mode, setMode] = useState<'reading' | 'editing' | 'confirming'>('reading')
  const [isBusy, setIsBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const editorReference = useRef<RichTextEditorHandle>(null)
  // A new array each render would redo this for nothing: key it on the words themselves.
  const termsKey = highlightTerms.join('\u0000')
  const shownBody = useMemo(
    () => highlightHtml(note.body, termsKey === '' ? [] : termsKey.split('\u0000')),
    [note.body, termsKey],
  )
  const wasEdited = note.updated_at !== note.created_at
  const openLabel = { bible_verse: 'Open in the Bible', commentary: 'Open the commentary note', devotional: 'Open the reading' }[note.item_type]

  // The editor is made when editing starts; fill it with the note as it is.
  useEffect(() => {
    if (mode === 'editing') {
      editorReference.current?.setHtml(note.body)
    }
  }, [mode, note.body])

  async function handleSave() {
    const editor = editorReference.current
    if (!editor || isBusy) {
      return
    }
    if (editor.isEmpty()) {
      setErrorMessage('Please write something in the note, or delete it.')
      return
    }
    setIsBusy(true)
    setErrorMessage('')
    try {
      onChanged(await updateNote(note.id, editor.getHtml()))
      setMode('reading')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The note could not be saved.')
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
      await deleteNote(note.id)
      onDeleted(note.id)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The note could not be deleted.')
      setIsBusy(false)
    }
  }

  return (
    <li className="note">
      {showTitle && <h3 className="note-title">{note.title}</h3>}
      <time dateTime={note.created_at}>
        {formatTime(note.created_at)}
        {wasEdited && ` (edited ${formatTime(note.updated_at)})`}
      </time>

      {mode === 'editing' ? (
        <div className="contact-form">
          <span id={`note-edit-label-${note.id}`} className="visually-hidden">
            Edit your note on {note.title}
          </span>
          <RichTextEditor ref={editorReference} placeholder="Write your note" labelledBy={`note-edit-label-${note.id}`} />
          <div className="note-actions">
            <button type="button" className="primary-button" disabled={isBusy} onClick={handleSave}>
              {isBusy ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="secondary-button" disabled={isBusy} onClick={() => setMode('reading')}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* The server cleans the note (a short list of tags, safe links) before it keeps it; the search words are
              only wrapped in <mark> in its text. */}
          <div className="note-body" dangerouslySetInnerHTML={{ __html: shownBody }} />
          {mode === 'confirming' ? (
            <div className="note-actions" role="alert">
              <span>Delete this note?</span>
              <button type="button" className="link-button danger" disabled={isBusy} onClick={handleDelete}>
                {isBusy ? 'Deleting…' : 'Yes, delete it'}
              </button>
              <button type="button" className="link-button" disabled={isBusy} onClick={() => setMode('reading')}>
                No, keep it
              </button>
            </div>
          ) : (
            <div className="note-actions">
              {onOpenItem && (
                <button type="button" className="link-button" onClick={() => onOpenItem(note)}>
                  {openLabel}
                  <span className="visually-hidden">: {note.title}</span>
                </button>
              )}
              <button type="button" className="link-button" onClick={() => setMode('editing')}>
                Edit
                <span className="visually-hidden"> the note on {note.title}</span>
              </button>
              <button type="button" className="link-button" onClick={() => setMode('confirming')}>
                Delete
                <span className="visually-hidden"> the note on {note.title}</span>
              </button>
            </div>
          )}
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

export default NoteCard
