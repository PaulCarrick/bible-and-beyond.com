import type { ReactNode } from 'react'

// Draws simple Markdown (paragraphs, ## headings, - and 1. lists, **bold** and *italic*) as React elements.
// Everything else is shown as plain text: nothing is ever inserted as HTML, so text from outside (an AI
// answer) cannot add tags, scripts or links to the page.

function renderInline(text: string): ReactNode[] {
  const pieces = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g)
  return pieces.map((piece, index) => {
    if (piece.startsWith('**') && piece.endsWith('**') && piece.length > 4) {
      return <strong key={index}>{piece.slice(2, -2)}</strong>
    }
    if ((piece.startsWith('*') && piece.endsWith('*')) || (piece.startsWith('_') && piece.endsWith('_'))) {
      if (piece.length > 2) {
        return <em key={index}>{piece.slice(1, -1)}</em>
      }
    }
    return piece
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

function MarkdownText({ markdown }: { markdown: string }) {
  return (
    <>
      {readBlocks(markdown).map((block, index) => {
        if (block.kind === 'heading') {
          return <h3 key={index}>{renderInline(block.text)}</h3>
        }
        if (block.kind === 'paragraph') {
          return <p key={index}>{renderInline(block.text)}</p>
        }
        const items = block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)
        return block.kind === 'bullets' ? <ul key={index}>{items}</ul> : <ol key={index}>{items}</ol>
      })}
    </>
  )
}

export default MarkdownText
