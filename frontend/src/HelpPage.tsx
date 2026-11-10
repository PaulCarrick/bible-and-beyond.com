import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchCopyrights } from './api'
import type { Copyright, Translation } from './types'
import type { View } from './views'

// "A, B and C"
function joinList(items: string[]) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

// The sections of the guide, in order, for the list of contents at the top.
const sections = [
  { id: 'help-getting-around', title: 'Finding your way around' },
  { id: 'help-search-everything', title: 'Search everything' },
  { id: 'help-read-bible', title: 'Reading the Bible' },
  { id: 'help-verse-menu', title: 'The verse menu' },
  { id: 'help-original-words', title: 'The Hebrew and Greek words' },
  { id: 'help-search-bible', title: 'Searching the Bible' },
  { id: 'help-commentaries', title: 'Commentaries' },
  { id: 'help-devotionals', title: 'Devotionals and daily emails' },
  { id: 'help-other-books', title: 'Other books' },
  { id: 'help-faq', title: 'FAQ: questions about the faith' },
  { id: 'help-accounts', title: 'Accounts (optional)' },
  { id: 'help-notes', title: 'Your notes' },
  { id: 'help-contact', title: 'Contact' },
  { id: 'help-tips', title: 'Handy shortcuts' },
  { id: 'help-texts', title: 'About the texts and credits' },
]

interface ScreenshotProps {
  // A file in public/help/, without ".webp".
  name: string
  width: number
  height: number
  alt: string
  caption: ReactNode
}

// A screenshot of the site, which opens full size in a new tab when clicked.
function Screenshot({ name, width, height, alt, caption }: ScreenshotProps) {
  const source = `/help/${name}.webp`
  return (
    <figure className="help-figure">
      <a href={source} target="_blank" rel="noopener" aria-label={`${alt} (opens the full-size picture in a new tab)`}>
        <img src={source} width={width} height={height} alt={alt} loading="lazy" decoding="async" />
      </a>
      <figcaption>{caption}</figcaption>
    </figure>
  )
}

interface PageLinkProps {
  view: View
  onNavigate: (view: View) => void
  children: ReactNode
}

// A link to another page of the site.
function PageLink({ view, onNavigate, children }: PageLinkProps) {
  return (
    <button type="button" className="link-button" onClick={() => onNavigate(view)}>
      {children}
    </button>
  )
}

interface HelpPageProps {
  translations: Translation[]
  onNavigate: (view: View) => void
}

// The user guide: every feature of the site with a screenshot, then where the texts come from (with the notices
// and credits that go with them). The screenshots are in public/help/; the owner's address in them is replaced
// by you@example.com.
function HelpPage({ translations, onNavigate }: HelpPageProps) {
  const [copyrights, setCopyrights] = useState<Copyright[]>([])
  const localBibles = translations.filter((translation) => translation.source === 'local').map((translation) => translation.code)
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

  function goToSection(id: string) {
    const section = document.getElementById(id)
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    section?.focus({ preventScroll: true })
  }

  return (
    <div className="welcome help-page">
      <h1>Help</h1>
      <p>
        Bible and Beyond is free. You can read and search everything on it without an account and without logging in.
        If you set up an account and log in, you can also write your own notes, have a devotional emailed to you each
        day, and ask to be allowed to put your own questions to the FAQ. This guide shows each part of the site.
        Click a picture to see it full size.
      </p>

      <nav className="help-contents" aria-label="Contents of this guide">
        <h2>Contents</h2>
        <ol>
          {sections.map((section) => (
            <li key={section.id}>
              <button type="button" className="link-button" onClick={() => goToSection(section.id)}>
                {section.title}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <section id="help-getting-around" tabIndex={-1} className="help-section">
        <h2>Finding your way around</h2>
        <p>
          Every page has the same three parts. At the top is the <strong>header</strong>: click the name or the round
          emblem to return to the <PageLink onNavigate={onNavigate} view="welcome">Welcome</PageLink> page. At the top right are{' '}
          <em>Set up account</em> and <em>Log in</em>; once you are logged in you see your email address,{' '}
          <em>My notes</em> and <em>Log out</em> there instead. On the left is the <strong>menu</strong>, grouped into
          the Bible, the commentaries, the devotionals, the other books, questions (the FAQ) and about (this Help page
          and Contact). On a phone the menu is hidden behind the menu button in the header.
        </p>
        <p>
          The Welcome page has a card for each part of the site, listing what is on it now (the Bibles, the
          commentaries, the devotionals and the other books), with buttons that open it. Each page has its own address,
          so you can bookmark it or share it, and the browser&rsquo;s Back button takes you back to where you were. A
          page keeps what you typed and how far you scrolled while you look at another one.
        </p>
        <Screenshot
          name="welcome"
          width={1152}
          height={1388}
          alt="The Welcome page with the menu on the left and a card for the Bible, the commentaries, the devotionals and the other books"
          caption="The Welcome page: the header, the menu on the left, a card for each part of the site, and Search everything at the foot."
        />
      </section>

      <section id="help-search-everything" tabIndex={-1} className="help-section">
        <h2>Search everything</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="searchAll">Search everything</PageLink> (in the menu, and under the cards on the Welcome page)
          looks for your words in the Bible, the commentaries, the devotionals and the other books at once. Type a word
          or a phrase, choose whether to match <em>all the words</em>, <em>any word</em> or the <em>exact phrase</em>,
          and press <em>Search</em>.
        </p>
        <p>
          The results come in groups, with the first five of each and a count. Press <em>Show more verses</em> (or
          notes, readings, passages) to see the next ones. In the Bible group the search finds whole words, so
          &ldquo;again&rdquo; does not also find &ldquo;against&rdquo;. Each result has a link that opens it where it
          was found: <em>Read in the Bible</em>, <em>Read the note</em>, <em>Read this reading</em> or{' '}
          <em>Read this chapter</em>. Press Back to return to your results.
        </p>
        <Screenshot
          name="search-all"
          width={1152}
          height={1764}
          alt="Search everything with results for love in the Bible and in the commentaries"
          caption="Search everything for “love”: the Bible verses first, then the commentary notes, each with a link to read it."
        />
      </section>

      <section id="help-read-bible" tabIndex={-1} className="help-section">
        <h2>Reading the Bible</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="read">Read the Bible</PageLink> shows a Bible a chapter at a time
          {localBibles.length > 0 ? ` (${joinList(localBibles)})` : ''}. Choose the Bible, the book and the chapter at
          the top, and if you like a verse, then press <em>Go</em>. The verse you asked for is marked with a coloured
          bar.
        </p>
        <p>
          You can keep scrolling: the next chapter (and the one before) loads by itself, on into the next book, and the
          choosers at the top follow along. Changing the Bible keeps your place, so you can compare a passage in another
          translation. To get back to the top, use <em>Back to top</em> (at the right of the choosers, or the blue
          button that appears as you scroll) or press the Home key.
          {licensed.length > 0
            ? ` The ${joinList(licensed)} can be searched but not read a chapter at a time, because their text is licensed.`
            : ''}
        </p>
        <Screenshot
          name="bible-reader"
          width={1152}
          height={1260}
          alt="The Bible reader showing Genesis 1 and the start of Genesis 2 in the Berean Standard Bible"
          caption="Reading Genesis in the Berean Standard Bible: one verse to a line, chapter after chapter."
        />
      </section>

      <section id="help-verse-menu" tabIndex={-1} className="help-section">
        <h2>The verse menu</h2>
        <p>
          Right-click a verse, or click (or tap) its small verse number, to open its menu. Resting the mouse pointer on
          a verse number shows a reminder of this. From the keyboard, Tab to the verse number and press Enter. If you have selected some text, right-clicking gives the browser&rsquo;s usual
          menu instead, so you can still copy. The menu has:
        </p>
        <ul className="welcome-tips">
          <li>
            <strong>Show in Context</strong>: the verse with the verses before and after it.
          </li>
          <li>
            <strong>Full Chapter</strong>: the whole chapter, with the verse marked.
          </li>
          <li>
            <strong>Other Translations</strong>: the same verse in every Bible stored on this site.
          </li>
          <li>
            <strong>Related Verses</strong>: cross references. <em>Points to</em> lists the verses this one points
            to, best first; <em>Pointed to by</em> lists the verses that point to it. Each related verse has its own
            links, so you can follow a chain of references.
          </li>
          <li>
            <strong>Original Words</strong>: the Hebrew or Greek words of the verse, with how to say them, what they
            mean and their Strong&rsquo;s numbers.
          </li>
          <li>
            <strong>Commentaries</strong>: what each commentary says about the verse, one tab per commentary.
          </li>
          <li>
            <strong>Notes</strong>: your own notes on the verse (you need to be logged in; see{' '}
            <button type="button" className="link-button" onClick={() => goToSection('help-notes')}>
              Your notes
            </button>
            ).
          </li>
        </ul>
        <p>
          Each of these opens in a window in place of the reading. <em>Back</em> returns to the window before, and the X
          or the Escape key closes them all and puts you back where you were reading. In Show in Context and Full
          Chapter, each verse number is a button that opens your notes on that verse.
        </p>
        <Screenshot
          name="verse-menu"
          width={1139}
          height={876}
          alt="The verse menu open on Genesis 1:1 with its seven choices"
          caption="The menu of Genesis 1:1, opened by right-clicking the verse."
        />
      </section>

      <section id="help-original-words" tabIndex={-1} className="help-section">
        <h2>The Hebrew and Greek words</h2>
        <p>
          In the Berean Standard Bible (BSB) you can <strong>click any English word</strong>, in the reader or in Show
          in Context, to see the Hebrew or Greek word it translates: the word itself, how to say it, its meaning and a
          dictionary entry, and the verses that use it, each with <em>Show in Context</em> and{' '}
          <em>Original Words</em>. The other Bibles show the words through <em>Original Words</em> in the verse menu,
          where each Strong&rsquo;s number opens the same entry.
        </p>
        <p>
          To find every verse that uses one Hebrew or Greek word, type its Strong&rsquo;s number in Search the Bible:
          for example <code>G25</code> (agapaō, to love) or <code>H7225</code> (reshith, beginning). The results show
          the word, with a link to its dictionary entry.
        </p>
        <Screenshot
          name="word"
          width={1152}
          height={1330}
          alt="The dictionary entry for the Hebrew word shamayim, heaven, with the verses that use it"
          caption="Clicking “heavens” in Genesis 1:1 opens the entry for the Hebrew word שָׁמַיִם (shamayim), used in 395 verses."
        />
      </section>

      <section id="help-search-bible" tabIndex={-1} className="help-section">
        <h2>Searching the Bible</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="bible">Search the Bible</PageLink>: type words or a phrase and press{' '}
          <em>Search for keyword or phrase</em>. The results are listed in Bible order, with your words in bold. Under
          each verse are links to Show in Context, Full Chapter, Other Translations, Related Verses, Original Words,
          Commentaries and Notes, the same as in the verse menu. Click the <em>Verse</em> or <em>Contents</em> heading
          of the list to sort the results by it, and <em>Clear Sort</em> to go back to Bible order.
        </p>
        <p>Open <strong>Search Options</strong> under the results to change how and where the search looks:</p>
        <ul className="welcome-tips">
          <li>
            <strong>Match ALL words, ANY word or the exact phrase.</strong> A phrase in quotation marks is kept
            together.
          </li>
          <li>
            <strong>Match whole words only.</strong> Without it, &ldquo;love&rdquo; also finds &ldquo;beloved&rdquo; and
            &ldquo;loved&rdquo;.
          </li>
          <li>
            <strong>Select Bibles to search.</strong> Choose one Bible, or press <em>Search in multiple versions</em> to
            tick several. The Bibles on this site are listed together, verse by verse.
            {licensed.length > 0
              ? ` The licensed Bibles (${joinList(licensed)}) can be ticked too: each is listed in a section of its own under the others, with its copyright notice. They always match all of the words, in Bible order, and their verses have no links.`
              : ''}
          </li>
          <li>
            <strong>Where to search.</strong> The entire Bible; a group of books (Old Testament, New Testament, the Law,
            History, Poetry, the Prophets, the Gospels and Acts, the Epistles, or Paul&rsquo;s letters, Romans to
            Philemon); or a range of books, such as Matthew to John.
          </li>
          <li>
            <strong>Results per page.</strong> <em>Automatic</em> fits as many as your screen holds; you can choose a
            fixed number instead.
          </li>
          <li>
            <strong>Filters.</strong> After a search, the number of results in each book. Click a book to see only its
            verses, and <em>Show all books</em> to see them all again.
          </li>
        </ul>
        <Screenshot
          name="bible-search"
          width={1152}
          height={2644}
          alt="Search results for love in the BSB and KJV, with an NIV section below and the search options open"
          caption="“love” searched in the BSB and the KJV together, with the NIV in its own section below, and the Search Options open."
        />
      </section>

      <section id="help-commentaries" tabIndex={-1} className="help-section">
        <h2>Commentaries</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="browse">Read the commentaries</PageLink> opens a list of the commentaries, each with what it
          covers. Choose a book and a chapter on any of them and press <em>Read</em>. In the reader you can scroll on
          from chapter to chapter, choose a verse to go to its note, or switch to another commentary at the same place
          to compare them. Each note has <em>Show in Context</em> and <em>Other Commentaries</em> links, and every
          Scripture reference in a note is a link to that verse. <em>All commentaries</em>, at the start of the
          choosers, takes you back to the list.
        </p>
        <Screenshot
          name="read-commentaries"
          width={1152}
          height={1225}
          alt="The list of commentaries, each with a book and chapter chooser and a Read button"
          caption="Read the commentaries: pick a book and chapter in any commentary and press Read."
        />
        <p>
          <PageLink onNavigate={onNavigate} view="commentary">Search the commentaries</PageLink> finds words in the notes of every commentary
          (or one you choose). Words match in any form, so &ldquo;love&rdquo; also finds &ldquo;loved&rdquo; and
          &ldquo;loving&rdquo;. The best matches come first; click the <em>Verse</em> heading to list them in Bible
          order instead. Each result shows the words around the match, with <em>Read the note</em> (the whole note),{' '}
          <em>Show in Context</em> (the verse) and <em>Notes</em> (your own notes on it). The same book limits and
          filters as in Search the Bible are in Search Options.
        </p>
        <Screenshot
          name="search-commentaries"
          width={1152}
          height={1631}
          alt="Commentary search results for love, best matches first, with the search options open"
          caption="Searching the commentaries for “love”: 7,695 notes, best matches first."
        />
      </section>

      <section id="help-devotionals" tabIndex={-1} className="help-section">
        <h2>Devotionals and daily emails</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="devotionals">Read the devotionals</PageLink> opens a list of the devotionals. A daily one,
          such as <em>Daily Light on the Daily Path</em>, has a morning and an evening reading for each day of the year
          and starts at today&rsquo;s date; others are read a chapter at a time. Choose the day (or the part and
          chapter) and press <em>Read</em>.
        </p>
        <Screenshot
          name="devotionals"
          width={1152}
          height={879}
          alt="The list of devotionals with month and day choosers or part and chapter choosers"
          caption="Read the devotionals: a daily devotional opens at today’s date."
        />
        <p>
          In the reader you can scroll on to the days or chapters before and after, and <em>Today</em> brings you back
          to today&rsquo;s reading. The Scripture references are links that open the verse. Each day has a{' '}
          <em>Notes</em> link for your own notes on that reading.
        </p>
        <Screenshot
          name="devotionals-open"
          width={1400}
          height={984}
          alt="The devotional reader showing the November 8 reading of Daily Light on the Daily Path"
          caption="Reading today’s Daily Light, with its references as links."
        />
        <p>
          <strong>Have it emailed to you each day.</strong> With an account whose email address is confirmed, open{' '}
          <em>Email me this devotional each day</em> above the reading, choose the time of day and your time zone (and,
          for a devotional read by chapters, the chapter to start with), and press <em>Email it to me each day</em>. The
          email arrives within five minutes of that time. You can change the time or stop the emails in the same place,
          and every email has a link that stops it.
        </p>
        <Screenshot
          name="devotional-email"
          width={1400}
          height={527}
          alt="The Email me this devotional each day panel with a time of day, a time zone and a button"
          caption="Choosing a time to receive the daily reading by email."
        />
      </section>

      <section id="help-other-books" tabIndex={-1} className="help-section">
        <h2>Other books</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="books">Read other books</PageLink> lists classic Christian books to read a chapter at a time,
          from Augustine and Aquinas to Bunyan, Wesley, Edwards, Chesterton and Tozer. Choose a part and a chapter and
          press <em>Read</em>. The reader works like the devotionals: scroll on through the chapters, follow the
          Scripture references, and use <em>Notes</em> on any chapter. <em>All books</em> returns to the list.
        </p>
        <Screenshot
          name="other-books"
          width={1152}
          height={1870}
          alt="The list of other books, each with part and chapter choosers and a Read button"
          caption="Read other books: every book with its parts and chapters."
        />
        <Screenshot
          name="other-books-open"
          width={1152}
          height={1250}
          alt="The book reader showing the introduction and preface of The Pursuit of God"
          caption="Reading The Pursuit of God by A. W. Tozer."
        />
        <p>
          <PageLink onNavigate={onNavigate} view="searchBooks">Search other books</PageLink> finds words or a phrase in all of the books or in
          one. Words match in any form. Choose the best matches first or the order of the books, and press{' '}
          <em>Read this chapter</em> on a result to open it there.
        </p>
        <Screenshot
          name="other-books-search"
          width={1152}
          height={1520}
          alt="Search results for love in the other books, each with Read this chapter"
          caption="Searching the other books for “love”: 376 passages."
        />
      </section>

      <section id="help-faq" tabIndex={-1} className="help-section">
        <h2>FAQ: questions about the faith</h2>
        <p>
          The <PageLink onNavigate={onNavigate} view="faq">FAQ</PageLink> answers common questions about God, Jesus, the Bible and the Christian
          life. Choose a question from the list (they are in groups) and press <em>Show the answer</em>. The answers
          are kept for a month, so one usually appears at once; when an answer is being written afresh it can take up
          to half a minute.
        </p>
        <Screenshot
          name="faq"
          width={1152}
          height={877}
          alt="The FAQ page with its list of questions open"
          caption="The list of questions, in groups."
        />
        <p>
          The answers are written by an AI (Google Gemini) from a Bible-centred, historic Christian point of view. Every
          Scripture reference in an answer is a link that opens the verse in a new tab, so the answer stays open. An AI
          can make mistakes, so check what it says against the Bible and talk over important questions with a pastor
          or a trusted Christian friend.
        </p>
        <p>
          Some questions also have <em>A note from the site owner</em>, in a box under the answer: the owner’s own
          words, not the AI’s. Their Bible quotations and the links in them open in a new tab, and some link to another
          answer on the FAQ page or to another page of this site.
        </p>
        <Screenshot
          name="faq-open"
          width={1152}
          height={1685}
          alt="The answer to How do I know God exists, with Scripture references as links and a note that an AI wrote it"
          caption="An answer, with its Scripture references as links and the note that an AI wrote it."
        />
        <p>
          <strong>Asking your own question.</strong> You can also ask questions of your own in your own words, in a box
          at the foot of the FAQ page. This is turned on for each account by hand, so:
        </p>
        <ol className="welcome-tips">
          <li>
            <PageLink onNavigate={onNavigate} view="register">Set up an account</PageLink> first.
          </li>
          <li>
            Then use the <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> form to ask for free-form questions to be turned on,
            giving the email address of your account.
          </li>
          <li>
            Once it is turned on, log in and open the FAQ: <em>Ask your own question</em> appears under the list. Write
            your question (up to 1,500 characters) and press <em>Ask</em>. You can ask up to 30 questions a day.
          </li>
        </ol>
        <Screenshot
          name="faq-own-question"
          width={1400}
          height={984}
          alt="The FAQ page with the Ask your own question box under the list of questions"
          caption="Ask your own question, shown to accounts it has been turned on for."
        />
      </section>

      <section id="help-accounts" tabIndex={-1} className="help-section">
        <h2>Accounts (optional)</h2>
        <p>
          You do not need an account to read or search anything. An account lets you write notes, receive a devotional
          by email each day and, on request, ask your own questions in the FAQ.
        </p>
        <ul className="welcome-tips">
          <li>
            <strong>Setting one up.</strong> Click <PageLink onNavigate={onNavigate} view="register">Set up account</PageLink> at the top of
            the page and enter your email address and a password twice (at least 8 characters). Your first
            name, last name and phone number are optional. You are logged in at once.
          </li>
          <li>
            <strong>Confirming your address.</strong> We email you a link; click it within three days. Notes work
            straight away, but the daily emails need a confirmed address. If the email does not come, the reminder at
            the top of the page has <em>Send it again</em>.
          </li>
          <li>
            <strong>Logging in and out.</strong> <PageLink onNavigate={onNavigate} view="login">Log in</PageLink> and <em>Log out</em> are at the
            top right. You stay logged in on that browser for 30 days.
          </li>
          <li>
            <strong>A forgotten password.</strong> On the Log in page choose <em>Forgot your password?</em>, enter your
            address, and use the link we email you within an hour to choose a new password.
          </li>
          <li>
            <strong>Your address</strong> is used only for the site&rsquo;s own emails (the confirmation link, a password
            reset and any daily devotional you choose). Your name and phone number are kept with your account; only
            the site&rsquo;s administrators can see them.
          </li>
        </ul>
      </section>

      <section id="help-notes" tabIndex={-1} className="help-section">
        <h2>Your notes</h2>
        <p>
          When you are logged in, you can write notes on a Bible verse, a commentary note, a devotional reading or a
          chapter of one of the other books. Choose <em>Notes</em> in the verse menu, under a search result, beside a
          commentary note or under the heading of a reading or chapter, or click a verse number in Show in Context. Write
          in the box (with bold, italic, headings, lists, quotations and links) and press <em>Save note</em>. Your
          earlier notes on the same item are listed below it. A note on a verse shows whichever Bible you are reading.
          Your notes are private: nobody else can see them.
        </p>
        <Screenshot
          name="note"
          width={1280}
          height={953}
          alt="The notes window for John 1:1 with a note being written"
          caption="Writing a note on John 1:1."
        />
        <p>
          <PageLink onNavigate={onNavigate} view="notes">My notes</PageLink> (at the top of the page when you are logged in) lists all of your
          notes, newest first, 25 to a page. You can show one kind only, search them (the words you searched for are
          highlighted), and use <em>Open in the Bible</em>, <em>Open the commentary note</em> or{' '}
          <em>Open the reading</em> to go to what a note is about. Each note can be edited or deleted (you are asked
          before it is deleted). <em>Add a note</em> writes a new note on any Bible verse.
        </p>
        <Screenshot
          name="my-notes"
          width={1400}
          height={1746}
          alt="The My notes page with four notes and the form to add a note on a Bible verse"
          caption="My notes, with a note on a verse, a reading and a commentary note, and the form to add one."
        />
      </section>

      <section id="help-contact" tabIndex={-1} className="help-section">
        <h2>Contact</h2>
        <p>
          Use the <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> form for questions, corrections, suggestions, or to ask
          for your own FAQ questions to be turned on (see{' '}
          <button type="button" className="link-button" onClick={() => goToSection('help-faq')}>
            FAQ
          </button>
          ). Enter your name, your email address (so we can reply), a phone number if you like, and your message, and
          press <em>Send Message</em>. The form is protected from spam by Google reCAPTCHA, which works in the
          background: there is no box to tick.
        </p>
        <Screenshot
          name="contact"
          width={1152}
          height={925}
          alt="The contact form with name, email, phone and message fields and a Send Message button"
          caption="The contact form."
        />
      </section>

      <section id="help-tips" tabIndex={-1} className="help-section">
        <h2>Handy shortcuts</h2>
        <ul className="welcome-tips">
          <li>
            <strong>Open a verse in a new tab.</strong> Hold Shift or Ctrl (Cmd on a Mac) while clicking Show in Context,
            Full Chapter or a Scripture reference, or click it with the middle mouse button, to open that verse in the
            Bible reader in a new tab and keep your place.
          </li>
          <li>
            <strong>Escape</strong> closes the windows (Show in Context, Related Verses and the rest) and returns to
            where you were.
          </li>
          <li>
            <strong>Home</strong> (or Back to top) goes to the top of the page in the readers.
          </li>
          <li>
            <strong>The browser&rsquo;s Back button</strong> returns to the page before, at the place you left it.
          </li>
          <li>
            <strong>Search tips.</strong> Put a phrase in quotation marks to keep its words together. In the
            commentaries, the devotionals and the other books, words match in any form. In Search the Bible, a
            Strong&rsquo;s number such as G25 or H7225 finds every verse that uses that Hebrew or Greek word.
          </li>
        </ul>
      </section>

      <section id="help-texts" tabIndex={-1} className="help-section">
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
          . <PageLink onNavigate={onNavigate} view="copyright">Bible copyright notices</PageLink>
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
          ). The other Bibles, the commentaries, the devotionals and the other books are in the public domain. The full
          credits and notices are on the <PageLink onNavigate={onNavigate} view="copyright">Bible copyright notices</PageLink> page.
        </p>
      </section>
    </div>
  )
}

export default HelpPage
