import type { Book, BookCount } from './types'

const testaments = [
  { label: 'Old Testament', code: 'OT' },
  { label: 'New Testament', code: 'NT' },
]

interface ResultFiltersProps {
  books: Book[]
  // How many results each book has.
  bookCounts: BookCount[]
  // The book the results are kept to (null for all of them).
  selectedBook: number | null
  onSelectBook: (book: number | null) => void
}

// Keep the results of a search to one book of the Bible: each book with how many results it has. It is shown in
// the Search Options.
function ResultFilters({ books, bookCounts, selectedBook, onSelectBook }: ResultFiltersProps) {
  const countsByBook = new Map(bookCounts.map((entry) => [entry.book_number, entry.count]))
  const totalAcrossBooks = bookCounts.reduce((sum, entry) => sum + entry.count, 0)

  return (
    <div className="panel filters">
      <h2>Filters</h2>
      <button
        type="button"
        className={selectedBook === null ? 'filter active' : 'filter'}
        onClick={() => onSelectBook(null)}
      >
        All ({totalAcrossBooks.toLocaleString()})
      </button>
      {testaments.map((testament) => {
        const testamentBooks = books.filter((book) => book.testament === testament.code && countsByBook.has(book.number))
        if (testamentBooks.length === 0) {
          return null
        }
        const testamentTotal = testamentBooks.reduce((sum, book) => sum + (countsByBook.get(book.number) ?? 0), 0)
        return (
          <div key={testament.code}>
            <h3>
              {testament.label} ({testamentTotal.toLocaleString()})
            </h3>
            {testamentBooks.map((book) => (
              <button
                type="button"
                key={book.number}
                className={selectedBook === book.number ? 'filter active' : 'filter'}
                onClick={() => onSelectBook(book.number)}
              >
                {book.name} ({countsByBook.get(book.number)})
              </button>
            ))}
          </div>
        )
      })}
    </div>
  )
}

export default ResultFilters
