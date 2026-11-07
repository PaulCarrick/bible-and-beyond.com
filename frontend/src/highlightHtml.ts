import { escapeRegularExpression } from './highlight'

// Wraps every match of the search words in <mark>, in the text of a note's HTML and nowhere else: tags and
// their attributes (a link's address, say) are never touched. The words match in any case and any part of
// a word, as the search on the server does. The note's HTML has been cleaned by the server, and it is only
// parsed here (nothing in it runs), so the result is as safe as the note was.
export function highlightHtml(html: string, terms: string[]): string {
  const words = [...new Set(terms.filter((term) => term !== ''))]
  if (words.length === 0) {
    return html
  }
  // The longest first, so "grace" wins over "gra" where both would match at the same place.
  const pattern = new RegExp(
    `(${words
      .sort((first, second) => second.length - first.length)
      .map(escapeRegularExpression)
      .join('|')})`,
    'gi',
  )
  const body = new DOMParser().parseFromString(html, 'text/html').body
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    textNodes.push(node as Text)
  }
  for (const node of textNodes) {
    const pieces = node.data.split(pattern)
    if (pieces.length < 2) {
      continue
    }
    const replacement = document.createDocumentFragment()
    // With one capture group, split puts every match at an odd index.
    pieces.forEach((piece, index) => {
      if (piece === '') {
        return
      }
      if (index % 2 === 1) {
        const mark = document.createElement('mark')
        mark.textContent = piece
        replacement.appendChild(mark)
      } else {
        replacement.appendChild(document.createTextNode(piece))
      }
    })
    node.replaceWith(replacement)
  }
  return body.innerHTML
}
