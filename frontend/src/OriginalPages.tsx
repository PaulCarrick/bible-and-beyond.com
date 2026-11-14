import { libraryPageAddress } from './api'
import type { OriginalPages as OriginalPagesType } from './types'

interface OriginalPagesProps {
  pages: OriginalPagesType
}

// The pages of the PDF a reading came from ("Preserve original pages"), one under another as pictures, loaded
// only as they come into view. The text read from them is what search finds; the reader can switch to it.
function OriginalPages({ pages }: OriginalPagesProps) {
  const numbers = Array.from({ length: Math.max(0, pages.last - pages.first + 1) }, (_, index) => pages.first + index)
  return (
    <div className="original-pages">
      {numbers.map((number) => (
        <img
          key={number}
          src={libraryPageAddress(pages.document, number)}
          alt={`Page ${number} of the original`}
          loading="lazy"
          decoding="async"
          width={1000}
          height={1294}
        />
      ))}
    </div>
  )
}

export default OriginalPages
