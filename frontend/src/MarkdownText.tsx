import { Fragment } from 'react'
import type { ReactNode } from 'react'

// Draws simple Markdown (paragraphs, ## headings, - and 1. lists, **bold** and *italic*) as React elements.
// Everything else is shown as plain text: nothing is ever inserted as HTML, so text from outside (an AI
// answer) cannot add tags, scripts or links to the page. The only links are the ones the caller passes in
// (for example the Scripture references the server found), drawn as buttons that call back.

export interface TextLink {
  // The exact words to turn into a link, such as "Romans 8:38–39".
  text: string
  label: string
  onClick: () => void
}

// Turns every occurrence of a link's words in a piece of text into a button.
function renderLinks(text: string, links: TextLink[], keyPrefix: string): ReactNode[] {
  if (links.length === 0) {
    return [text]
  }
  // The longest first, so "1 John 4:1" is not taken for "John 4:1".
  const sorted = [...links].sort((first, second) => second.text.length - first.text.length)
  const escaped = sorted.map((link) => link.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`(${escaped.join('|')})`, 'g')
  return text.split(pattern).map((piece, index) => {
    const link = sorted.find((candidate) => candidate.text === piece)
    if (!link) {
      return piece
    }
    return (
      <button key={`${keyPrefix}-${index}`} type="button" className="link-button" aria-label={link.label} onClick={link.onClick}>
        {piece}
      </button>
    )
  })
}

function renderInline(text: string, links: TextLink[]): ReactNode[] {
  const pieces = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g)
  return pieces.map((piece, index) => {
    if (piece.startsWith('**') && piece.endsWith('**') && piece.length > 4) {
      return <strong key={index}>{renderLinks(piece.slice(2, -2), links, String(index))}</strong>
    }
    if ((piece.startsWith('*') && piece.endsWith('*')) || (piece.startsWith('_') && piece.endsWith('_'))) {
      if (piece.length > 2) {
        return <em key={index}>{renderLinks(piece.slice(1, -1), links, String(index))}</em>
      }
    }
    return <Fragment key={index}>{renderLinks(piece, links, String(index))}</Fragment>
  })
}

type Block =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'bullets' | 'numbers'; items: string[] }

function readBlocks(markdown: string): Block[] {
  const blocks: Block[] = []
  let paragraph: string[] = []

  function endParagraph() {
    if (paragraph.length > 0) {
      blocks.push({ kind: 'paragraph', text: paragraph.join(' ') })
      paragraph = []
    }
  }

  for (const rawLine of markdown.split('\n')) {
    const line = rawLine.trim()
    const heading = line.match(/^#{1,6}\s+(.*)$/)
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    const number = line.match(/^\d+[.)]\s+(.*)$/)
    const last = blocks[blocks.length - 1]

    if (line === '') {
      endParagraph()
    } else if (heading) {
      endParagraph()
      blocks.push({ kind: 'heading', text: heading[1].replace(/\*\*/g, '') })
    } else if (bullet || number) {
      endParagraph()
      const kind = bullet ? 'bullets' : 'numbers'
      const item = (bullet ?? number)![1]
      if (last && last.kind === kind) {
        last.items.push(item)
      } else {
        blocks.push({ kind, items: [item] })
      }
    } else if (paragraph.length === 0 && last && (last.kind === 'bullets' || last.kind === 'numbers') && rawLine.startsWith(' ')) {
      // An indented line goes on with the list item above it.
      last.items[last.items.length - 1] += ` ${line}`
    } else {
      paragraph.push(line)
    }
  }
  endParagraph()
  return blocks
}

function MarkdownText({ markdown, links = [] }: { markdown: string; links?: TextLink[] }) {
  return (
    <>
      {readBlocks(markdown).map((block, index) => {
        if (block.kind === 'heading') {
          return <h3 key={index}>{renderInline(block.text, links)}</h3>
        }
        if (block.kind === 'paragraph') {
          return <p key={index}>{renderInline(block.text, links)}</p>
        }
        const items = block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, links)}</li>)
        return block.kind === 'bullets' ? <ul key={index}>{items}</ul> : <ol key={index}>{items}</ol>
      })}
    </>
  )
}

export default MarkdownText
