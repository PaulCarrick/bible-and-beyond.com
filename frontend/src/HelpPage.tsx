import { useEffect, useState } from 'react'
import { fetchCopyrights } from './api'
import type { Copyright, Translation } from './types'
import type { View } from './views'

// "A, B and C"
function joinList(items: string[]) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

interface HelpPageProps {
  translations: Translation[]
  onNavigate: (view: View) => void
}

// How to use the site, and where its texts come from (with the notices and credits that go with them).
function HelpPage({ translations, onNavigate }: HelpPageProps) {
  const [copyrights, setCopyrights] = useState<Copyright[]>([])
  const licensed = translations
    .filter((translation) => translation.source === 'api_bible')
    .map((translation) => (translation.code === 'MSG' ? 'The Message' : translation.code))

  // The notices of the licensed Bibles come from API.Bible with the text (the server keeps them for a
  // day). If they cannot be had, the page still says where the Bibles come from and links to the full notices.
  useEffect(() => {
    fetchCopyrights()
      .then(setCopyrights)
      .catch(() => setCopyrights([]))
  }, [])

  return (
    <div className="welcome help-page">
      <h1>Help</h1>

      <h2>How to use it</h2>
      <ul className="welcome-tips">
        <li>
          <strong>Search everything at once.</strong> The search box under the cards on the{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('welcome')}>
            Welcome
          </button>{' '}
          page (or{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('searchAll')}>
            Search everything
          </button>{' '}
          in the menu) looks in the Bible, the commentaries, the devotionals and the other books together, and lists a few
          of each with <em>Show more</em>. Each result opens where it was found.
        </li>
        <li>
          <strong>Choose where to start.</strong> Read the commentaries, Read the devotionals and Read other books open on
          a list: pick a book and chapter (or a month and day) on any of them and press <em>Read</em>. In the reader,
          the link at the start of the choosers (<em>All commentaries</em>, <em>All devotionals</em>,{' '}
          <em>All books</em>) takes you back to the list.
        </li>
        <li>
          <strong>Right-click a verse</strong> while reading (or click its number) for a menu: Show in Context, Full
          Chapter, Other Translations, Related Verses (cross references), Original Words (the Hebrew or Greek),
          Commentaries and Notes. Search results have the same links under each verse.
        </li>
        <li>
          <strong>Click a word of the BSB</strong> to see the Hebrew or Greek word behind it, with its meaning and every
          verse that uses it.
        </li>
        <li>
          <strong>Follow the references.</strong> A Scripture reference inside a commentary or a devotional is a link to
          the verse. Back returns to where you were, and Escape closes the window.
        </li>
        <li>
          <strong>Open a verse in a new tab.</strong> Hold Shift or Ctrl (Cmd on a Mac) while clicking Show in Context,
          Full Chapter or a Scripture reference, or click it with the middle mouse button, to open that verse in the
          Bible reader in a new tab and keep your place here.
        </li>
        <li>
          <strong>Keep scrolling.</strong> The readers load the next and the previous chapter as you go. The Home key,
          or the Back to top button, takes you to the top of the page.
        </li>
        <li>
          <strong>Search tips.</strong> Put a phrase in quotation marks to keep its words together. In the commentaries,
          the devotionals and the other books, words match in any form, so &ldquo;love&rdquo; also finds
          &ldquo;loved&rdquo;. Search the Bible matches parts of words unless you choose whole words (so
          &ldquo;love&rdquo; also finds &ldquo;beloved&rdquo;); Search everything matches whole words in the Bible. A
          Strong&rsquo;s number such as G25 or H7225 finds every verse that uses that Hebrew or Greek word.
        </li>
      </ul>

      <h2>Accounts, notes and emails</h2>
      <p>
        You never need an account to read or search. With one (<em>Set up account</em> at the top of the page) you can
        write notes and have a devotional emailed to you each day.
      </p>
      <ul className="welcome-tips">
        <li>
          <strong>Confirm your email address.</strong> We email you a link when you set up the account. Notes can be
          written at once; the daily emails need the address to be confirmed. If you forget your password, use
          &ldquo;Forgot your password?&rdquo; on the Log in page.
        </li>
        <li>
          <strong>Notes.</strong> Choose <em>Notes</em> on a verse, a commentary note, a devotional reading or a chapter
          of one of the other books, or click a
          verse number in Show in Context. Your notes are private. <em>My notes</em> (at the top of the page) lists
          them all, with search, and lets you add, edit and delete them and open what each is about.
        </li>
        <li>
          <strong>Daily devotional emails.</strong> On the devotionals page, open &ldquo;Email me this devotional each
          day&rdquo; and choose a time and your time zone. Each email has a link that stops it, and you can stop or
          change it on the same page.
        </li>
        <li>
          <strong>Common questions about the faith.</strong>{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('faq')}>
            FAQ
          </button>{' '}
          (under Questions in the menu) answers common questions about God, Jesus, the Bible and the Christian life.
          The answers are written by an AI (Google Gemini) and may contain mistakes, so check them against the Bible.
        </li>
        <li>
          <strong>Questions or corrections?</strong> Use{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('contact')}>
            Contact
          </button>{' '}
          in the menu.
        </li>
      </ul>

      <h2>About the texts</h2>
      <p>
        The Bibles you can read here, the commentaries, the devotionals and the other books are in the public domain.
        {licensed.length > 0
          ? ` The ${joinList(licensed)} are licensed to us through API.Bible; they can be searched but not read a chapter at a time.`
          : ''}{' '}
        The Hebrew and Greek data comes from STEP Bible and the cross references from OpenBible.info, both under a
        Creative Commons licence.
      </p>

      <h2>Licensed Bibles</h2>
      <p>
        Scripture for the NIV, NASB and The Message is provided through{' '}
        <a href="https://api.bible" target="_blank" rel="noreferrer">
          API.Bible
        </a>
        .{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('copyright')}>
          Bible copyright notices
        </button>
      </p>
      {copyrights.length > 0 && (
        <ul className="help-copyrights">
          {copyrights.map((copyright) => (
            <li key={copyright.code}>
              <strong>{copyright.code}</strong> {copyright.copyright}
            </li>
          ))}
        </ul>
      )}

      <h2>Credits</h2>
      <p>
        Hebrew and Greek data from{' '}
        <a href="https://www.stepbible.org" target="_blank" rel="noreferrer">
          STEP Bible
        </a>{' '}
        (
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
          CC BY 4.0
        </a>
        ). Cross references from{' '}
        <a href="https://www.openbible.info/labs/cross-references/" target="_blank" rel="noreferrer">
          OpenBible.info
        </a>{' '}
        (
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
          CC BY 4.0
        </a>
        ). The other Bibles, the commentaries, the devotionals and the other books are in the public domain. The full credits and notices
        are on the{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('copyright')}>
          Bible copyright notices
        </button>{' '}
        page.
      </p>
    </div>
  )
}

export default HelpPage
