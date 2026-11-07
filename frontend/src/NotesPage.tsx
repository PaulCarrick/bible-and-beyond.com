import { useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchAllNotes, saveNote } from './api'
import NoteCard from './NoteCard'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { Book, Note } from './types'

interface NotesPageProps {
  books: Book[]
  // The Bible a new note on a verse is filed under (the verse itself is the same in every Bible).
  translation: string
}

const typeChoices = [
  { value: 'all', label: 'All notes' },
  { value: 'bible_verse', label: 'Bible verses' },
  { value: 'commentary', label: 'Commentaries' },
  { value: 'devotional', label: 'Devotionals' },
]

// Everything the logged-in visitor has written, newest first, with a way to add a note on a Bible verse
// and to edit or delete any note. (A note on a commentary note or a devotional reading is added from the
// Notes link beside it.)
function NotesPage({ books, translation }: NotesPageProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [filter, setFilter] = useState('all')
  const [errorMessage, setErrorMessage] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [bookNumber, setBookNumber] = useState('')
  const [chapterText, setChapterText] = useState('')
  const [verseText, setVerseText] = useState('')
  const [addError, setAddError] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const editorReference = useRef<RichTextEditorHandle>(null)
  const userId = user?.id ?? null

  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchAllNotes(controller.signal)
      .then(setNotes)
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId])

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    const editor = editorReference.current
    if (!editor || isSaving) {
      return
    }
    setAddError('')
    const chapter = Number.parseInt(chapterText, 10)
    const verse = Number.parseInt(verseText, 10)
    if (bookNumber === '' || Number.isNaN(chapter) || Number.isNaN(verse) || chapter < 1 || verse < 1) {
      setAddError('Please choose a book and give a chapter and a verse.')
      return
    }
    if (editor.isEmpty()) {
      setAddError('Please write something in the note.')
      return
    }
    setIsSaving(true)
    try {
      const note = await saveNote(
        { item_type: 'bible_verse', source_code: translation, book_number: Number(bookNumber), chapter, verse },
        editor.getHtml(),
      )
      setNotes((current) => [note, ...(current ?? [])])
      editor.clear()
      setChapterText('')
      setVerseText('')
      setIsAdding(false)
    } catch (error) {
      setAddError(error instanceof Error ? error.message : 'Your note could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  if (user === null) {
    return (
      <div className="notes-page">
        <h1>My notes</h1>
        <p>
          Notes are private to your account.{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            Log in
          </button>{' '}
          or{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('register')}>
            set up an account
          </button>{' '}
          to see and write notes.
        </p>
      </div>
    )
  }

  const shown = (notes ?? []).filter((note) => filter === 'all' || note.item_type === filter)

  return (
    <div className="notes-page">
      <h1>My notes</h1>
      <p>
        Your notes on Bible verses, commentary notes and devotional readings. To write one on a commentary note or a
        devotional reading, use the Notes link beside it.
      </p>

      <div className="notes-toolbar">
        <label className="inline-label">
          Show
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            {typeChoices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        {!isAdding && (
          <button type="button" className="primary-button" onClick={() => setIsAdding(true)}>
            Add a note
          </button>
        )}
      </div>

      {/* The editor stays in the page while the form is closed, so it is never made twice. */}
      <form className="contact-form notes-add" onSubmit={handleAdd} hidden={!isAdding}>
        <h2>Add a note on a Bible verse</h2>
        <div className="notes-verse-fields">
          <label className="contact-field">
            Book
            <select value={bookNumber} onChange={(event) => setBookNumber(event.target.value)}>
              <option value="">Choose a book</option>
              {books.map((book) => (
                <option key={book.number} value={book.number}>
                  {book.name}
                </option>
              ))}
            </select>
          </label>
          <label className="contact-field">
            Chapter
            <input type="number" min={1} max={200} value={chapterText} onChange={(event) => setChapterText(event.target.value)} />
          </label>
          <label className="contact-field">
            Verse
            <input type="number" min={1} max={200} value={verseText} onChange={(event) => setVerseText(event.target.value)} />
          </label>
        </div>
        <span id="notes-add-label" className="visually-hidden">
          Your note
        </span>
        <RichTextEditor ref={editorReference} placeholder="Write your note" labelledBy="notes-add-label" />
        {addError && (
          <p className="error" role="alert">
            {addError}
          </p>
        )}
        <div className="note-actions">
          <button type="submit" className="primary-button" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save note'}
          </button>
          <button type="button" className="link-button" disabled={isSaving} onClick={() => setIsAdding(false)}>
            Cancel
          </button>
        </div>
      </form>

      {errorMessage && <p className="error">{errorMessage}</p>}
      {notes === null && !errorMessage && <p>Loading…</p>}
      {notes !== null && shown.length === 0 && (
        <p>{notes.length === 0 ? 'You have not written any notes yet.' : 'You have no notes of that kind.'}</p>
      )}
      {shown.length > 0 && (
        <ul className="note-list">
          {shown.map((note) => (
            <NoteCard
              key={note.id}
              note={note}
              showTitle
              onChanged={(changed) => setNotes((current) => (current ?? []).map((entry) => (entry.id === changed.id ? changed : entry)))}
              onDeleted={(id) => setNotes((current) => (current ?? []).filter((entry) => entry.id !== id))}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

export default NotesPage
