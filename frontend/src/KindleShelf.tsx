import type { KindleBook } from './api'
import { kindleCoverAddress } from './api'

interface KindleShelfProps {
  books: KindleBook[]
  isHidden: boolean
  // The page's own heading, when the collection has only Kindle books (no reader list above).
  pageHeading?: string
}

// Kindle books (2026-11-19): books read in Amazon's Kindle web reader, listed under the Devotionals or Other books kept
// on this site. Only the link is kept here: each opens in its own window, signed in to the reader's own Amazon
// account (Amazon refuses to be shown inside another site), so it works for those who have the book in their own
// Kindle library.
function KindleShelf({ books, isHidden, pageHeading }: KindleShelfProps) {
  if (books.length === 0) {
    return null
  }
  return (
    <section className="kindle-shelf" hidden={isHidden} aria-labelledby={pageHeading ? undefined : 'kindle-shelf-heading'}>
      {pageHeading ? <h1>{pageHeading}</h1> : <h2 id="kindle-shelf-heading">On Kindle</h2>}
      <p className="kindle-shelf-note">
        These open in Amazon&rsquo;s Kindle reader in a new window. Sign in there with your own Amazon account; a book opens
        if it is in your Kindle library.
      </p>
      <ul className="kindle-books">
        {books.map((book) => (
          <li key={book.id} className="kindle-book">
            {book.cover ? (
              <img className="kindle-book-cover" src={kindleCoverAddress(book.cover)} alt="" loading="lazy" />
            ) : (
              <div className="kindle-book-cover kindle-book-no-cover" aria-hidden="true">
                📖
              </div>
            )}
            <div className="kindle-book-details">
              <strong>{book.title}</strong>
              {book.author && <span className="kindle-book-author">{book.author}</span>}
              <button
                type="button"
                className="secondary-button"
                onClick={() => window.open(book.address, '_blank', 'noopener,noreferrer')}
              >
                Open in Kindle ↗
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default KindleShelf
