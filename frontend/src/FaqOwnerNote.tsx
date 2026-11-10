import { useContext } from 'react'
import type { MouseEvent } from 'react'
import { AccountContext } from './AccountContext'
import { viewForAddress } from './pageAddress'

interface FaqOwnerNoteProps {
  // The note as HTML, written on the Drupal "FAQ notes" page and cleaned by the server with an allowlist
  // (ml-service/faq_notes.py): no scripts, no styles, no event attributes, only safe links.
  html: string
  // Shows another FAQ question's answer on this page.
  onShowQuestion: (question: string) => void
}

// The site owner's own note on the question shown, in a box between the AI's answer and its AI note.
//
// Its links are ordinary links, so they also open in a new tab with Ctrl, Cmd or the middle button. The
// server gives the links to a verse (/?read=BSB&book=..., with &strong=G0264 to open a lexicon entry over
// it) and to other websites target="_blank", so they open in a new tab and the FAQ stays open. A plain
// click on a link to another answer (/faq?question=the question's words) shows that answer here, and one
// on a page of the site (/search, /read ...) opens that page, like the sidebar.
function FaqOwnerNote({ html, onShowQuestion }: FaqOwnerNoteProps) {
  const { onNavigate } = useContext(AccountContext)

  function handleClick(event: MouseEvent<HTMLDivElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return
    }
    const link = (event.target as HTMLElement).closest('a')
    const href = link?.getAttribute('href') ?? ''
    if (!link || link.target || !href.startsWith('/') || href.startsWith('//')) {
      return
    }
    const address = new URL(href, window.location.origin)
    const question = address.searchParams.get('question')
    if (address.pathname.replace(/\/+$/, '') === '/faq' && question) {
      event.preventDefault()
      onShowQuestion(question)
      return
    }
    if (address.search === '') {
      event.preventDefault()
      onNavigate(viewForAddress(address.pathname))
    }
  }

  return (
    <aside className="faq-owner-note" aria-labelledby="faq-owner-note-heading">
      <h2 id="faq-owner-note-heading">A note from the site owner</h2>
      {/* The HTML is cleaned on the server, so it is safe to draw as HTML here. */}
      <div onClick={handleClick} dangerouslySetInnerHTML={{ __html: html }} />
    </aside>
  )
}

export default FaqOwnerNote
