function escapeRegularExpression(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Wraps every match of a search term in <strong>. The text itself is never changed.
export function highlight(text: string, terms: string[], wholeWords: boolean) {
  const alternatives = terms
    .map((term) => escapeRegularExpression(term))
    .map((term) => (wholeWords ? `\\b${term}\\b` : term))
  if (alternatives.length === 0) {
    return text
  }
  const pieces = text.split(new RegExp(`(${alternatives.join('|')})`, 'i'))
  // With one capture group, split puts every match at an odd index.
  return pieces.map((piece, index) =>
    index % 2 === 1 ? <strong key={index}>{piece}</strong> : piece,
  )
}
