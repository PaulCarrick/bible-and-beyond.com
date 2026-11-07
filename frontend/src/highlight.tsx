import type { MouseEvent, ReactElement } from 'react'
import { verseButtonProps } from './verseAddress'
import type { VerseInBible } from './verseAddress'

export function escapeRegularExpression(text: string) {
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

export interface LinkOptions {
  className: string
  // Whether the buttons are in the tab order. Hundreds of Strong's links per chapter are not; the
  // handful of references in a note are.
  isTabbable: boolean
  titleFor: (code: string, shownText: string) => string
  // For links to verses: where a link's verse is, so Shift, Ctrl or Cmd with a click (or the middle button)
  // opens it in the Bible reader in a new tab. Not set for Strong's numbers.
  newTabVerse?: (code: string) => VerseInBible
}

export const strongLinkOptions: LinkOptions = {
  className: 'word-link',
  isTabbable: false,
  titleFor: (code) => `Strong's ${code}`,
}

// Like highlight, and also makes the words that have a Strong's number clickable. The two can
// overlap (a search phrase over several linked words), so the text is cut wherever either starts
// or stops, and the pieces of one linked word are put back inside one button.
// For Strong's numbers the buttons stay out of the tab order: there would be hundreds in a chapter,
// and the Original Words window lists the same numbers for keyboard use.
export function highlightLinked(
  text: string,
  terms: string[],
  wholeWords: boolean,
  links: [number, number, string][],
  onChoose: (code: string, element: HTMLElement) => void,
  // How the linked words look and behave. The default suits Strong's numbers on a Bible verse.
  options: LinkOptions = strongLinkOptions,
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
          className={options.className}
          tabIndex={options.isTabbable ? 0 : -1}
          title={options.titleFor(link[2], group.map((piece) => piece.text).join(''))}
          {...(options.newTabVerse
            ? verseButtonProps(options.newTabVerse(link[2]), (element) => onChoose(link[2], element))
            : { onClick: (event: MouseEvent<HTMLButtonElement>) => onChoose(link[2], event.currentTarget) })}
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

// An excerpt of a commentary note: the server wraps each word it found in \u0001 and \u0002.
// Line breaks become spaces so the excerpt reads as one passage.
export function renderExcerpt(excerpt: string) {
  const nodes: (string | ReactElement)[] = []
  excerpt
    .replace(/\s*\n+\s*/g, ' ')
    .split('\u0001')
    .forEach((segment, index) => {
      if (index === 0) {
        nodes.push(segment)
        return
      }
      const [found, ...rest] = segment.split('\u0002')
      nodes.push(<strong key={index}>{found}</strong>, rest.join('\u0002'))
    })
  return nodes
}
