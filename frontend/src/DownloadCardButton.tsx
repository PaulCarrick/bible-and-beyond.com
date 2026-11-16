import { useState } from 'react'
import { fetchVerseCard } from './api'
import type { VerseInBible } from './verseAddress'

interface DownloadCardButtonProps {
  verse: VerseInBible
  reference: string
}

// "Download Card" among a search result's verse links, before Notes (added 2026-11-16 at the owner's request):
// asks the server for that verse's card, made as on the Verse of the day page (the words in a large script over a
// random verse a day picture, day_cards.py), and saves it at once as a JPEG named after the verse. Only under
// the Bibles stored on this site: the licensed ones have no verse links.
function DownloadCardButton({ verse, reference }: DownloadCardButtonProps) {
  const [isMaking, setIsMaking] = useState(false)
  const [problem, setProblem] = useState('')

  async function download() {
    if (isMaking) {
      return
    }
    setIsMaking(true)
    setProblem('')
    try {
      const card = await fetchVerseCard(verse)
      const link = document.createElement('a')
      link.href = card.image
      link.download = `${reference} ${verse.translation}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '.jpg'
      document.body.append(link)
      link.click()
      link.remove()
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'The card could not be made.')
    } finally {
      setIsMaking(false)
    }
  }

  return (
    <>
      <button type="button" className="link-button context-link" onClick={download} disabled={isMaking} title="Save this verse as a picture">
        {isMaking ? 'Making the card…' : 'Download Card'}
        <span className="visually-hidden"> of {reference}</span>
      </button>
      {problem && (
        <span className="error" role="alert">
          {problem}
        </span>
      )}
    </>
  )
}

export default DownloadCardButton
