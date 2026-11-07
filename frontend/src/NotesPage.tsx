import { useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AccountContext } from './AccountContext'
import { fetchNotePage, saveNote } from './api'
import NoteCard from './NoteCard'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'
import type { Book, NotePage } from './types'

interface NotesPageProps {
  books: Book[]
  // The Bible a new note on a verse is filed under (the verse itself is the same in every Bible).
  translation: string
}

const notesPerPage = 25

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
  const [result, setResult] = useState<NotePage | null>(null)
  const [filter, setFilter] = useState('all')
  // What is typed in the search box, and what the list is actually searched for (set when it is submitted).
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  // Changed to ask for the list again (after a note is added or deleted).
  const [reload, setReload] = useState(0)
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
    fetchNotePage({ query, itemType: filter, page, perPage: notesPerPage }, controller.signal)
      .then((loaded) => {
        // Deleting the last note of the last page leaves that page empty: show the one before.
        if (loaded.notes.length === 0 && loaded.total > 0 && page > 1) {
          setPage(Math.ceil(loaded.total / notesPerPage))
        } else {
          setErrorMessage('')
          setResult(loaded)
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId, query, filter, page, reload])

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    setQuery(searchText.trim())
    setPage(1)
  }

  function clearSearch() {
    setSearchText('')
    setQuery('')
    setPage(1)
  }

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
      await saveNote(
        { item_type: 'bible_verse', source_code: translation, book_number: Number(bookNumber), chapter, verse },
        editor.getHtml(),
      )
      // The new note is the newest: show the list from its start, without a search or kind that hides it.
      setFilter('all')
      setSearchText('')
      setQuery('')
      setPage(1)
      setReload((count) => count + 1)
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

  const pageCount = result ? Math.max(1, Math.ceil(result.total / notesPerPage)) : 1
  const isFiltered = query !== '' || filter !== 'all'

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
          <select
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value)
              setPage(1)
            }}
          >
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

      <form className="notes-search" role="search" onSubmit={handleSearch}>
        <input
          type="search"
          value={searchText}
          maxLength={200}
          placeholder="Search your notes"
          aria-label="Search your notes"
          onChange={(event) => setSearchText(event.target.value)}
        />
        <button type="submit" className="primary-button">
          Search
        </button>
        {(query !== '' || searchText !== '') && (
          <button type="button" className="link-button" onClick={clearSearch}>
            Clear search
          </button>
        )}
      </form>

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
      {result === null && !errorMessage && <p>Loading…</p>}
      {result !== null && (
        <p className="notes-count" role="status">
          {result.total === 0
            ? isFiltered
              ? 'No notes match.'
              : 'You have not written any notes yet.'
            : `${result.total} ${result.total === 1 ? 'note' : 'notes'}${isFiltered ? (result.total === 1 ? ' matches' : ' match') : ''}${
                query !== '' ? ` “${query}”` : ''
              }.`}
        </p>
      )}
      {result !== null && result.notes.length > 0 && (
        <ul className="note-list">
          {result.notes.map((note) => (
            <NoteCard
              key={note.id}
              note={note}
              showTitle
              onChanged={(changed) =>
                setResult((current) =>
                  current ? { ...current, notes: current.notes.map((entry) => (entry.id === changed.id ? changed : entry)) } : current,
                )
              }
              onDeleted={() => setReload((count) => count + 1)}
            />
          ))}
        </ul>
      )}

      {result !== null && pageCount > 1 && (
        <nav className="pagination" aria-label="Pages of notes">
          <button type="button" disabled={page <= 1} onClick={() => setPage(1)}>
            First
          </button>
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {pageCount}
          </span>
          <button type="button" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
            Next
          </button>
          <button type="button" disabled={page >= pageCount} onClick={() => setPage(pageCount)}>
            Last
          </button>
        </nav>
      )}
    </div>
  )
}

export default NotesPage
