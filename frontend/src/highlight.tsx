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

// Where a search term matches the text, as [start, end] pairs.
function findHighlightRanges(text: string, terms: string[], wholeWords: boolean) {
  const alternatives = terms
    .map((term) => escapeRegularExpression(term))
    .map((term) => (wholeWords ? `\\b${term}\\b` : term))
  if (alternatives.length === 0) {
    return []
  }
  const ranges: [number, number][] = []
  for (const match of text.matchAll(new RegExp(alternatives.join('|'), 'gi'))) {
    ranges.push([match.index, match.index + match[0].length])
  }
  return ranges
}

// Like highlight, and also makes the words that have a Strong's number clickable. The two can
// overlap (a search phrase over several linked words), so the text is cut wherever either starts
// or stops, and the pieces of one linked word are put back inside one button.
// The buttons stay out of the tab order: there would be hundreds in a chapter. The Original Words
// window lists the same numbers for keyboard use.
export function highlightLinked(
  text: string,
  terms: string[],
  wholeWords: boolean,
  links: [number, number, string][],
  onChoose: (strongCode: string) => void,
) {
  const ranges = findHighlightRanges(text, terms, wholeWords)
  const cuts = new Set<number>([0, text.length])
  for (const [start, end] of ranges) {
    cuts.add(start)
    cuts.add(end)
  }
  for (const [start, end] of links) {
    cuts.add(start)
    cuts.add(end)
  }
  const positions = [...cuts].sort((first, second) => first - second)

  const pieces: { text: string; bold: boolean; link: [number, number, string] | undefined }[] = []
  for (let index = 0; index < positions.length - 1; index += 1) {
    const start = positions[index]
    const end = positions[index + 1]
    pieces.push({
      text: text.slice(start, end),
      bold: ranges.some(([rangeStart, rangeEnd]) => rangeStart <= start && end <= rangeEnd),
      link: links.find(([linkStart, linkEnd]) => linkStart <= start && end <= linkEnd),
    })
  }

  const nodes = []
  for (let index = 0; index < pieces.length; index += 1) {
    const link = pieces[index].link
    const group = [pieces[index]]
    while (link && index + 1 < pieces.length && pieces[index + 1].link === link) {
      index += 1
      group.push(pieces[index])
    }
    const content = group.map((piece, position) =>
      piece.bold ? <strong key={position}>{piece.text}</strong> : piece.text,
    )
    nodes.push(
      link ? (
        <button
          type="button"
          key={nodes.length}
          className="word-link"
          tabIndex={-1}
          title={`Strong's ${link[2]}`}
          onClick={() => onChoose(link[2])}
        >
          {content}
        </button>
      ) : (
        <span key={nodes.length}>{content}</span>
      ),
    )
  }
  return nodes
}
