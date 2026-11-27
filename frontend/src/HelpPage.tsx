import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchCopyrights } from './api'
import MusicLicenceNote from './MusicLicenceNote'
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
  { id: 'help-listen', title: 'Listening' },
  { id: 'help-verse-menu', title: 'The verse menu' },
  { id: 'help-original-words', title: 'The Hebrew and Greek words' },
  { id: 'help-search-bible', title: 'Searching the Bible' },
  { id: 'help-commentaries', title: 'Commentaries' },
  { id: 'help-devotionals', title: 'Devotionals and daily emails' },
  { id: 'help-other-books', title: 'Other books' },
  { id: 'help-music', title: 'Christian media' },
  { id: 'help-maps', title: 'Maps' },
  { id: 'help-faq', title: 'FAQ: questions about the faith' },
  { id: 'help-accounts', title: 'Accounts (optional)' },
  { id: 'help-verse-a-day', title: 'A verse a day and text messages' },
  { id: 'help-notes', title: 'Your notes' },
  { id: 'help-lists', title: 'My lists' },
  { id: 'help-conversations', title: 'Conversations' },
  { id: 'help-prayer-wall', title: 'Prayer Wall' },
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
  // Whether a song of the Christian music section is published (its section is left out until one is).
  hasMusic?: boolean
  // The maps section shows only when a map is published.
  hasMaps?: boolean
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// The user guide: every feature of the site with a screenshot, then where the texts come from (with the notices
// and credits that go with them). The screenshots are in public/help/; the owner's address in them is replaced
// by you@example.com.
function HelpPage({ translations, onNavigate, hasMusic = false, hasMaps = false, siteTitle }: HelpPageProps) {
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
        {siteTitle} is free. You can read and search everything on it without an account and without logging in.
        If you set up an account and log in, you can also write your own notes, have a devotional or a Bible verse sent
        to you each day (by email, and by text message if you like), get the prayer list each week, make music
        playlists, keep lists of search results, and ask to be allowed to put your own questions to the FAQ, to write in Conversations and on the
        Prayer Wall, or to mark the maps with your own pins, routes and notes. This guide shows each part of the site.
        Click a picture to see it full size.
      </p>
      <p>
        Prefer to watch? The{' '}
        <PageLink onNavigate={onNavigate} view="tutorial">tutorial video</PageLink>{' '}
        is a fourteen-minute narrated tour of the whole site, including the maps, the verse a day and text messages.
      </p>

      <nav className="help-contents" aria-label="Contents of this guide">
        <h2>Contents</h2>
        <ol>
          {sections.filter((section) => (hasMusic || section.id !== 'help-music') && (hasMaps || section.id !== 'help-maps')).map((section) => (
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
          emblem to return to the <PageLink onNavigate={onNavigate} view="welcome">Welcome</PageLink> page. At the far top
          right is the <strong>account icon</strong> (a circle with a head and shoulders, or your own picture): point at it
          or click it for its menu, <em>Log in</em> and <em>Set up account</em>, or once you are logged in{' '}
          <em>Account settings</em>, <em>My notes</em>, <em>My lists</em>, <em>My cards</em> and <em>Log out</em>, and{' '}
          <em>My scheduled tasks</em> if you are in a group (such as your church&rsquo;s greeters): it lists the tasks
          you are scheduled for, each with its date, whether it is confirmed, what it involves and any note for you.
          There, <em>Add a task</em> lets you ask for one of your group&rsquo;s tasks on one of its dates in the
          next two months (it shows as not confirmed until the leader confirms it, and you are emailed then), and{' '}
          <em>Remove</em> takes you off a coming one. Your group leader is emailed either way. On the left is the{' '}
          <strong>menu</strong>: Welcome and Search everything at the top, then groups for the Bible, the commentaries,
          the devotionals, the other books, Christian media, maps, questions (the FAQ), today (Verse of the day and
          Devotional of the day), members (Conversations, the Prayer Wall and Public lists) and about (this Help page,
          the tutorial video, Contact, Privacy, the text message terms and the posting policy). When the site&rsquo;s
          administrators list other websites they use, an <em>External sites</em> group links to them (each opens in a
          new tab). The groups start closed to
          keep the menu short: a small arrow (▶) beside a group&rsquo;s name shows it is closed. Click the name to open
          it and see its pages (the arrow turns down), and click it again to close it. The group of the page you are on
          opens by itself. On a phone the menu is hidden behind the menu button in the header.
        </p>
        <p>
          The Welcome page has a card for each part of the site, listing what is on it now (the Bibles, the
          commentaries, the devotionals, the other books, the media and the maps), with buttons that open it, and below
          them the latest post in Conversations. Each page has its own address,
          so you can bookmark it or share it, and the browser&rsquo;s Back button takes you back to where you were. A
          page keeps what you typed and how far you scrolled while you look at another one.
        </p>
        <Screenshot
          name="welcome"
          width={1152}
          height={1560}
          alt="The Welcome page with the menu on the left, its groups closed, cards for the Bible, the commentaries, the devotionals, the other books, Christian media and the maps, and the latest Conversations post"
          caption="The Welcome page: the header, the menu on the left (click a group to open it), and a card for each part of the site."
        />
        <Screenshot
          name="account-menu"
          width={1152}
          height={560}
          alt="The account icon at the top right, showing the member's picture, with its menu open: the name and address, Account settings, My notes, My lists and Log out"
          caption="The account icon's menu, opened by pointing at the icon (or clicking it)."
        />
      </section>

      <section id="help-search-everything" tabIndex={-1} className="help-section">
        <h2>Search everything</h2>
        <p>
          <PageLink onNavigate={onNavigate} view="searchAll">Search everything</PageLink> (in the menu, and under the cards on the Welcome page)
          looks for your words in the Bible, the commentaries, the devotionals, the other books, the Christian media, the maps and the FAQ at once. Type a word
          or a phrase, choose whether to match <em>all the words</em>, <em>any word</em> or the <em>exact phrase</em>,
          and press <em>Search</em>.
        </p>
        <p>
          The results come in groups, with the first five of each and a count. Press <em>Show more verses</em> (or
          notes, readings, passages, songs, questions) to see the next ones; a song is found by its title, its author or its words, and <em>Play this song</em> opens it; an FAQ question is found by its own words, the site owner&rsquo;s note under it or its answer, and <em>Show the answer</em> opens it on the FAQ page. In the Bible group the search finds whole words, so
          &ldquo;again&rdquo; does not also find &ldquo;against&rdquo;. Each result has a link that opens it where it
          was found: <em>Read in the Bible</em>, <em>Read the note</em>, <em>Read this reading</em> or{' '}
          <em>Read this chapter</em>. Press Back to return to your results.
        </p>
        <p>
          <strong>Searching with AI.</strong> If your account may ask its own FAQ questions, the Match list also offers{' '}
          <em>Use AI to find related passages</em>. It finds what is closest in <em>meaning</em> to your words, even
          when the words differ: a search for &ldquo;the beatitudes&rdquo; finds commentary notes and readings on
          &ldquo;Blessed are the poor in spirit&rdquo;, which never use the word. An AI suggests the Bible verses; the
          commentaries, devotionals, other books and songs are those nearest in meaning, closest first. The same
          choice is on <em>Search the commentaries</em>, <em>Search other books</em> and <em>Search the media</em>. The
          AI can be wrong, so read each result where it was found.
        </p>
        <p>
          <strong>Searching the Internet Archive.</strong> Every search page also offers <em>Search the Internet Archive</em>{' '}
          in its Match list, with no account needed. It searches inside the books and documents of the{' '}
          <a href="https://archive.org" target="_blank" rel="noopener noreferrer">
            Internet Archive
          </a>{' '}
          (or its recordings, on <em>Search the media</em>) and shows a few lines around your words. Older books open with{' '}
          <em>Read on archive.org</em>. Books still under copyright show <em>Borrow for an hour on archive.org</em>: the
          Internet Archive lends them free, an hour at a time, to anyone signed in on archive.org with a free Archive
          account (set one up there once). The loan is between you and the Internet Archive; this site only finds the
          book.
        </p>
        <Screenshot
          name="search-all"
          width={1152}
          height={1700}
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

      <section id="help-listen" tabIndex={-1} className="help-section">
        <h2>Listening</h2>
        <p>
          In <PageLink onNavigate={onNavigate} view="read">Read the Bible</PageLink>, press <strong>▶ Listen</strong>{' '}
          beside a chapter&rsquo;s name, or choose <em>Listen from here</em> on a verse, to hear it read aloud. The verse
          being read is highlighted and kept on the screen, and the reading goes on into the next chapter by itself. A
          bar at the foot of the screen has Pause (then Resume) and Stop, and lets you choose the voice and the speed
          (both are remembered on this device). Clicking the verse named on the bar brings it back into view. Leaving
          the page stops the reading.
        </p>
        <p>
          The voice is your device&rsquo;s own, so it sounds different on each computer or phone, and nothing is sent
          anywhere. The licensed Bibles (NIV, NASB and The Message) are not read in the reader, so they cannot be read
          aloud.
        </p>
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
            <strong>Listen from here</strong>: reads the Bible aloud from this verse (see <em>Listening</em> below).
          </li>
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
          width={1152}
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
          Commentaries and Notes, the same as in the verse menu, and <em>Download Card</em>, which saves the verse as a
          picture (the words over a photograph, as on <em>Verse of the day</em>) to share. Click the <em>Verse</em> or <em>Contents</em> heading
          of the list to sort the results by it, and <em>Clear Sort</em> to go back to Bible order.
        </p>
        <p>The list under the search box chooses how your words are matched:</p>
        <ul className="welcome-tips">
          <li>
            <strong>Match ALL words, ANY word or the exact phrase.</strong> A phrase in quotation marks is kept
            together.
          </li>
          <li>
            <strong>Use AI to find related verses.</strong> For accounts that may ask their own FAQ questions (see the
            FAQ section below for how to ask for it), this extra choice has an AI (Google&rsquo;s Gemini) suggest up to
            30 verses about what you describe, such as &ldquo;comfort when someone has died&rdquo;, and lists them from
            the Bibles on this site in Bible order. The AI can be wrong, so read each verse in context. Up to 50 new AI
            searches a day; the licensed Bibles are not searched this way.
          </li>
          <li>
            <strong>Search the Internet Archive.</strong> Searches the books and documents of the Internet Archive
            instead (see Search everything above).
          </li>
        </ul>
        <p>Open <strong>Search Options</strong> under the results to change where the search looks:</p>
        <ul className="welcome-tips">
          <li>
            <strong>Match whole words only.</strong> Without it, &ldquo;love&rdquo; also finds &ldquo;beloved&rdquo; and
            &ldquo;loved&rdquo;.
          </li>
          <li>
            <strong>Use AI to find related verses.</strong> For accounts that may ask their own FAQ questions (see the
            FAQ section below for how to ask for it), this extra choice has an AI (Google&rsquo;s Gemini) suggest up to
            30 verses about what you describe, such as &ldquo;comfort when someone has died&rdquo;, and lists them from
            the Bibles on this site in Bible order. The AI can be wrong, so read each verse in context. Up to 50 new AI
            searches a day; the licensed Bibles are not searched this way.
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
          height={1900}
          alt="Search results for love in the BSB, with the search options open"
          caption="“love” searched in the Berean Standard Bible, with the Search Options open."
        />
        <p>
          <strong>Searching with AI.</strong> If your account may ask its own FAQ questions, choose <em>Use AI to find
          related verses</em> in the list under the search box (no need to open Search Options), describe what you are looking for in your own words, and press{' '}
          <em>Find verses with AI</em>. The verses it suggests are listed like any search, with all the same links.
        </p>
        <Screenshot
          name="ai-search-results"
          width={1152}
          height={860}
          alt="AI search results for forgiving someone who hurt me, with the AI choice under the search box and Genesis 50:17 first"
          caption="An AI search for “forgiving someone who hurt me”: 30 verses suggested by Gemini, listed in Bible order with their links."
        />
        <Screenshot
          name="ai-search-options"
          width={1152}
          height={600}
          alt="The Match list under the search box, opened, with Use AI to find related verses chosen and its explanation below"
          caption="Use AI to find related verses, chosen in the list under the search box (shown only to accounts it has been turned on for)."
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
          width={1152}
          height={984}
          alt="The devotional reader showing today’s reading of Daily Light on the Daily Path"
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
          width={875}
          height={377}
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
        <p>
          Under the list of devotionals or of other books there may be books <em>On Kindle</em>. These are not kept on
          this site: <em>Open in Kindle</em> opens them in Amazon&rsquo;s Kindle reader in a new window, where you sign in
          with your own Amazon account, and a book opens if it is in your Kindle library. Their words cannot be searched
          here.
        </p>
        <Screenshot
          name="other-books"
          width={1152}
          height={1700}
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
        <p>
          Among them is <em>The Apostles’ Creed</em>, the ancient statement of the Christian faith. Each of its
          statements is a link to a Bible verse it is drawn from, though it reads as ordinary text: rest the pointer on
          a statement to see which verse, and click it to read the verse in context (with Shift, Ctrl or Cmd, in a new
          tab).
        </p>
        <Screenshot
          name="apostles-creed"
          width={1152}
          height={1010}
          alt="The Apostles’ Creed in the book reader, with a tooltip reading Show Luke 1:35 in context over a statement"
          caption="The Apostles’ Creed: the pointer on “who was conceived by the Holy Spirit” shows its verse."
        />
        <p>
          Every book also has an address of its own that opens it directly, such as{' '}
          <em>{window.location.host}/books?book=apostles-creed</em>, for a bookmark or to share.
        </p>
      </section>

      {hasMusic && (
        <section id="help-music" tabIndex={-1} className="help-section">
          <h2>Christian media</h2>
          <p>
            <PageLink onNavigate={onNavigate} view="music">Listen to the media</PageLink> lists hymns, songs and talks by title. Open one (click its
            title) to see its player and its words; press play. Starting another pauses the first, and closing a song stops it. A recording keeps playing while
            you read another page of the site (a video pauses, since it could not be seen). Some songs show their words
            as a page of a hymnal (a picture or a PDF) rather than as text; a PDF also has a link to open it in a new
            tab, for phones that cannot show it in the page. Some are on <strong>Spotify</strong>: they open with
            Spotify&apos;s own player, which plays them in full if you are signed in to Spotify in this browser and
            30-second previews otherwise. A Spotify item cannot go in a playlist.
          </p>
          <Screenshot
            name="music-open"
            width={1152}
            height={1250}
            alt="The Christian media page with Amazing Grace closed and It Is Well with My Soul open, showing its video player and its words"
            caption="Listen to the media: one song open, with its player and its words."
          />
          <p>
            <strong>Playlists</strong> (when you are logged in): each song has a checkbox at the right. Tick the songs you
            want; a box appears near the top of the page, under <em>Your playlists</em>: give the playlist a name and
            press <em>Save as a playlist</em>. The songs play in the order of the page until you change it. Your
            playlists are in <em>Your playlists</em> at the top of the page (click it to open it). Choose one and press <em>Play</em>: each song opens and plays in turn, and
            the next starts when one ends (on some phones you may need to press play on each song). Click a song in the
            playlist's list to play from that song on. <em>Edit</em> lets you change it in one place: drag a song by its handle
            (⠿) to move it, or use its up and down arrows, and <em>Remove</em> takes it out; and under them <em>Add songs</em> lists the songs not in it (choose one, or
            several with Cmd or Ctrl held, and press <em>Add</em>; they go at the end); press <em>Save changes</em> when it
            is right. <em>Change this playlist</em> ticks its songs so you can add or take
            some away and save under the same name (the order is kept, new songs go at the end);{' '}
            <em>Delete this playlist</em> removes it. Your playlists are yours alone unless you share one: if the
            site's administrators have allowed your account to share, <em>Share on Public lists</em> puts the chosen playlist
            on <PageLink onNavigate={onNavigate} view="publicLists">Public lists</PageLink>, where everyone can see and play
            it (listed with the shared lists, marked &ldquo;Playlist&rdquo;), and <em>Copy link</em> gives you its address to
            send to someone. <em>Stop sharing</em> takes it off again. On Public lists, a logged-in visitor can{' '}
            <em>Copy to my playlists</em>. <em>Export this playlist</em> saves it in a file, which <em>Import</em> on My
            lists reads back.
          </p>
          <Screenshot
            name="playlist-edit"
            width={1152}
            height={900}
            alt="Your playlists open, editing a playlist: each song with a drag handle, up and down arrows and Remove, then the Add songs list"
            caption="Editing a playlist: drag a song by its handle to move it, remove one, or add others from the list."
          />
          <p>
            <PageLink onNavigate={onNavigate} view="searchMusic">Search the media</PageLink> finds a song by its title, its author, its
            words or its keywords (words the site's administrator gives it, listed first), and <em>Play this song</em> on a result takes you to it. When you are logged in, each result also has
            a checkbox: tick songs (from as many searches as you like), give the playlist a name in the box above the
            results and press <em>Save as a playlist</em>. The songs play in the order you ticked them, and the playlist is
            then under <em>Your playlists</em> on the Listen to the media page.
          </p>
          <Screenshot
            name="music-search"
            width={1152}
            height={1010}
            alt="Search the media with the word grace, showing Amazing Grace with grace in bold and Play this song"
            caption="Searching the media for “grace”."
          />
          <p>
            <MusicLicenceNote />
          </p>
        </section>
      )}

      {hasMaps && (
        <section id="help-maps" tabIndex={-1} className="help-section">
          <h2>Maps</h2>
          <p>
            <PageLink onNavigate={onNavigate} view="maps">View the maps</PageLink> shows the maps of the lands and journeys of the Bible.
            Press <em>Open this map</em> to see one: drag it to move about, and zoom in and out with the + and − buttons,
            the mouse wheel or a pinch on a phone. <em>Full screen</em> gives it the whole window (Escape or{' '}
            <em>Leave full screen</em> returns). Under the map are what it shows, where it came from, and the verses it
            goes with; click a verse to read it in the Bible (with Shift, Ctrl or Cmd held, in a new tab), and Back
            returns to the map.
          </p>
          <Screenshot
            name="maps"
            width={1152}
            height={720}
            alt="View the maps: a card for each map with a small picture, its verses and an Open this map button"
            caption="View the maps: each map with its verses."
          />
          <Screenshot
            name="map-open"
            width={1152}
            height={1250}
            alt="A map of Palestine in the time of Jesus, open with zoom buttons and Full screen, showing a member's pins, a blue route and a dotted red route shared by another member"
            caption="An open map, with a member's own pins and route (solid) and a route another member shared (dotted)."
          />
          <p>
            <PageLink onNavigate={onNavigate} view="searchMaps">Search the maps</PageLink> finds a map by its title, description,
            keywords or verses; type a verse such as <em>Acts 13:4</em> to find only the maps that go with it. Search
            everything lists maps too.
          </p>
          <Screenshot
            name="map-search"
            width={1152}
            height={700}
            alt="Search the maps for Galilee, finding Palestine in the time of Jesus with the word in bold and Open this map"
            caption="Searching the maps for “Galilee”."
          />
          <p>
            <strong>Your own notes, pins and routes</strong> (when you are logged in, for members an administrator has
            invited: ask through the <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> form, giving the
            email address of your account): on an open map,{' '}
            <em>Drop a pin</em> and then click or tap the place, and write a note for it if you wish; <em>Trace a route</em>{' '}
            and click or tap each point in turn (<em>Undo the last point</em> takes one back), then <em>Finish the
            route</em>, name it and choose its colour; <em>Add a note</em> writes a note on the whole map. A verse in a
            note, such as Acts 13:4, becomes a link. They are listed under the map with <em>Show on the map</em>,{' '}
            <em>Edit</em> and <em>Delete</em>. When you edit a pin, drag it to move it; when you edit a route, drag any
            of its points to move it; drag one of the small pale points between two to add a point there (or click it to
            add one halfway); right-click a point (long-press on a phone) to take it out; and <em>Add points at the
            end</em> and <em>Remove the last point</em> change its ends. Your pins and
            routes are kept as places on the map, not as a copy of it. Each map you have marked is also listed on{' '}
            <PageLink onNavigate={onNavigate} view="notes">My notes</PageLink>.
          </p>
          <Screenshot
            name="map-marks"
            width={1152}
            height={1150}
            alt="Your notes, pins and routes under a map: three pins, a route and a note, each with Show on the map, Edit and Delete, and a route under Shared with you"
            caption="Under the map: your pins, routes and notes, and what other members have shared with you."
          />
          <p>
            <strong>Sharing.</strong> Only you see your notes, pins and routes unless you share one: under{' '}
            <em>Share with</em> type the email address of another member who can use the maps and press <em>Add</em>
            (add as many as you like), then save. They see it under <em>Shared with you</em>, drawn dotted on the map,
            with your name; they cannot change it. Remove someone there to stop sharing with them.
          </p>
          <Screenshot
            name="map-mark-edit"
            width={1152}
            height={1100}
            alt="Changing a route: its points shown on the map to drag, and a form with its name, colour, note, Add points at the end, Remove the last point and Share with"
            caption="Changing a route: drag its points on the map, and change its name, colour, note and who it is shared with."
          />
        </section>
      )}

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
          width={1152}
          height={984}
          alt="The FAQ page with the Ask your own question box under the list of questions"
          caption="Ask your own question, shown to accounts it has been turned on for."
        />
      </section>

      <section id="help-accounts" tabIndex={-1} className="help-section">
        <h2>Accounts (optional)</h2>
        <p>
          You do not need an account to read or search anything. An account lets you write notes, make playlists, save lists of search results,
          receive a devotional, a verse a day or the prayer list by email, by text or both and, on request,
          ask your own questions in the FAQ, write in Conversations and on the Prayer Wall, and mark the maps.
        </p>
        <ul className="welcome-tips">
          <li>
            <strong>Setting one up.</strong> Click <PageLink onNavigate={onNavigate} view="register">Set up account</PageLink> at the top of
            the page and enter your email address and a password twice (at least 8 characters). Your first
            name, last name and phone number are optional. <strong>No email address?</strong> Leave it empty and give
            your cell phone number instead (US or Canadian): you then log in with that number, we text you a code to
            confirm it, and nothing is ever sent to you by email, so the devotional emails, the prayer list email and
            reply emails are not offered. Notes, lists, the Prayer Wall and texts (if you choose them) all work. On the same form you can choose how your messages are sent
            (email, text or both) and a verse a day
            (see{' '}
            <button type="button" className="link-button" onClick={() => goToSection('help-verse-a-day')}>
              A verse a day and text messages
            </button>
            ). You are logged in at once.
          </li>
          <li>
            <strong>Confirming your address.</strong> We email you a link; click it within three days. Notes work
            straight away, but the daily emails need a confirmed address. If the email does not come, the reminder at
            the top of the page has <em>Send it again</em>.
          </li>
          <li>
            <strong>Confirming your phone</strong> (an account set up with a phone number). We text you a 6-digit code;
            type it in the box at the foot of the page and press <em>Confirm</em>. It works for 15 minutes;{' '}
            <em>Text me a new code</em> sends another. Until then everything works except texts to you.
          </li>
          <li>
            <strong>Logging in and out.</strong> <PageLink onNavigate={onNavigate} view="login">Log in</PageLink> and <em>Log out</em> are in the
            account icon's menu at the top right. Log in with your email address, or with your phone number if your account was set up with one
            (written any way: 555-123-4567 works). You stay logged in on that browser for 30 days.
          </li>
          <li>
            <strong>A forgotten password.</strong> On the Log in page choose <em>Forgot your password?</em>, enter your
            address (or the phone number you log in with), and use the link we email (or text) you within an hour to
            choose a new password.
          </li>
          <li>
            <strong>Changing your password.</strong> While logged in, choose <em>Account settings</em> in the account
            icon's menu at the top right, and under <em>Change your password</em> type your current password and the new one twice
            (at least 8 characters). Any other device logged in to your account is logged out; the one you are using stays
            logged in.
          </li>
          <li>
            <strong>Account settings.</strong> Choose <em>Account settings</em> in the account icon's menu at the top right.
            There you can add a picture of yourself (<em>Your picture</em>: choose a photo and its middle is kept as a
            square; it shows in the account icon, and only you see it), change your phone number, how your messages
            are sent (<em>Send via Email</em>, <em>Send via SMS</em>, or both) and your verse-a-day choice (press{' '}
            <em>Save</em>), and change your password.
          </li>
          <li>
            <strong>Closing your account.</strong> At the foot of <em>My account</em>, <em>Close my account</em> asks for
            your password and closes it: you are logged out everywhere, you can no longer log in, and after one email
            saying it was closed the site sends you no more emails or texts. What you wrote is kept. To have it reopened,
            or deleted with everything in it, ask through the{' '}
            <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> page.
          </li>
          <li>
            <strong>Your address</strong> is used only for the site&rsquo;s own emails (the confirmation link, a password
            reset, and any devotional, verse a day, prayer list or reply notices you choose). Your name and phone number
            are kept with your account; only the site&rsquo;s administrators can see them. The{' '}
            <PageLink onNavigate={onNavigate} view="privacy">Privacy</PageLink> page says what is kept and why.
          </li>
        </ul>
        <Screenshot
          name="sign-up"
          width={1152}
          height={1340}
          alt="The Set up account form with a phone number, the cell number and text message boxes ticked, and Send me a verse a day ticked with a time and time zone"
          caption="Setting up an account, with texts and a verse a day chosen."
        />
        <Screenshot
          name="my-account"
          width={1152}
          height={1240}
          alt="My account: Your picture with Choose another picture and Remove the picture, the phone number, how messages are sent, and the verse a day"
          caption="Account settings: your picture, your phone, how messages are sent and your verse a day."
        />
      </section>

      <section id="help-verse-a-day" tabIndex={-1} className="help-section">
        <h2>A verse a day and text messages</h2>
        <p>
          <strong>Verse of the day and Devotional of the day.</strong> Under <em>Today</em> in the sidebar (no
          account needed), <em>Verse of the day</em> shows a well-known Bible verse chosen at random, and{' '}
          <em>Devotional of the day</em> today&rsquo;s reading from one of the daily devotionals (the evening reading
          after 5 pm), each written over a photograph. <em>Download the picture</em> saves it to share;{' '}
          <em>Show another</em> makes a new one; and a button opens the verse in the Bible or the whole reading. On the
          verse, the picture and its reference are links to the verse in the Bible too. In the verse a day email the
          verse, its reference and its picture are links to the verse on the site, and its text message carries the
          link.
        </p>
        <p>
          <strong>Make your own card.</strong> Under the verse of the day, choose a Bible, a verse and a background
          (each shown as a small picture), and the card appears. <em>Download the card</em> saves it. When you are
          logged in you can also send it: to someone on this site, chosen by name (they get it the way they chose on
          their account, by email, text or both), or to any email address you type. The email says it is from you,
          and replies go to your own email address. You can send up to 20 cards a day. When you are logged in,
          <em>Save to My cards</em> keeps the card on <strong>My cards</strong>, and every card you download or send
          is kept there too (in the menu of the account icon at the top
          right), where you can edit it (change its Bible, verse or background), download it again, send it or
          delete it. The verse of the day picture itself is not kept there.
        </p>
        <Screenshot
          name="verse-of-the-day"
          width={1152}
          height={1080}
          alt="Verse of the day: a Bible verse written over a photograph, with Download the picture, Show another and Read it in the Bible"
          caption="Verse of the day (Today in the menu): a new verse over a photograph each time."
        />
        <p>
          <strong>A verse a day.</strong> Tick <em>Send me a verse a day</em> when you set up your account, or later on{' '}
          <em>My account</em>, and choose a time of day and your time zone. Each day at that time (within five minutes)
          you get one Bible verse from the Berean Standard Bible, chosen at random from about 1,500 of the best-known
          verses and never the same two days running, with a link to read it in context. It comes by email, by text
          or both, as you chose (see below). It starts once your email address (or, if you log in with your phone, your
          phone number) is confirmed. To stop it, untick the box on My
          account and press <em>Save</em>, or use the link at the foot of any of its emails.
        </p>
        <p>
          <strong>Email, text or both.</strong> Under <em>How should we send you messages?</em> (when you set up your
          account, or later on My account) tick <em>Send via Email</em>, <em>Send via SMS</em> or both. The daily
          devotional, the verse a day, the weekly prayer list and reply notices then come that way. At least one stays
          ticked: to switch from one to the other, tick the new one first, then untick the old one. Everyone starts with
          email.
        </p>
        <p>
          <strong>Picture messages.</strong> Tick <em>Send Multimedia Messages</em> (in the same place) to get the
          verse a day and the daily devotional as a picture: the verse, or the reading&rsquo;s opening words, written in
          large lettering over a photograph chosen at random. The picture comes at the top of the email and, if you get
          texts, as a picture message (MMS) with the text; your carrier may charge more for picture messages. The
          prayer list and reply notices stay as words.
        </p>
        <p>
          <strong>Text messages.</strong> <em>Send via SMS</em> can be ticked only once you give a US or Canadian
          phone number (it is written as +1 (555) 123-4567 as you type) and tick <em>This is a cell (mobile)
          number</em>; until then it is greyed out. You get a welcome text to confirm. A text is short, with a link to
          the full reading, verse, list or reply. Texts need a confirmed email address (or a confirmed phone number, for
          an account set up with one). Your mobile carrier may charge
          for texts (message and data rates may apply). Reply <strong>STOP</strong> to any text to end them
          (<strong>START</strong> turns them back on), or <strong>HELP</strong> for help; or untick{' '}
          <em>Send via SMS</em> on My account. If you chose texts only and they stop (you replied STOP), your messages
          come by email until you turn texts back on, so you miss nothing. The emails about your account (confirming
          your address, a password reset) always come by email and are never texted, except for an account set up with
          a phone number, whose code and reset link are texted.
        </p>
        <p>
          <strong>Messages from a group.</strong> A deacon or other leader may add you to a group on the site. Its
          messages, verse cards and picture messages come the way you chose above. Each email shows only the
          leader&rsquo;s address, never the other members&rsquo;, and a reply goes to the leader. At its foot, a link
          stops everything from that group. Emails the leader has scheduled (such as every first Monday) have two more
          links: one stops just that scheduled email, the other all of the group&rsquo;s scheduled emails; with either
          you stay in the group and still get what the leader sends. Ask the leader if you want them back.
        </p>
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
          width={1152}
          height={953}
          alt="The notes window for John 1:14 with a note being written"
          caption="Writing a note on John 1:14."
        />
        <p>
          <PageLink onNavigate={onNavigate} view="notes">My notes</PageLink> (in the account icon's menu at the top right when you are logged in) lists all of your
          notes, newest first, 25 to a page. You can show one kind only, search them (the words you searched for are
          highlighted), and use <em>Open in the Bible</em>, <em>Open the commentary note</em> or{' '}
          <em>Open the reading</em> to go to what a note is about. Each note can be edited or deleted (you are asked
          before it is deleted). <em>Add a note</em> writes a new note on any Bible verse. If you add notes, pins or
          routes to the maps, each map you have marked is one entry too, listing them, with <em>Open the map</em> (choose{' '}
          <em>Maps</em> under Show to see only those); change or delete them on the map.
        </p>
        <Screenshot
          name="my-notes"
          width={1152}
          height={1420}
          alt="The My notes page with four notes and the form to add a note on a Bible verse"
          caption="My notes, with a note on a verse, a reading and a commentary note, and the form to add one."
        />
      </section>

      <section id="help-lists" tabIndex={-1} className="help-section">
        <h2>My lists</h2>
        <p>
          When you are logged in, every search (Search everything, the Bible, the commentaries, the other books, the
          media and the maps) has a checkbox at the right of each result. Tick the ones you want to keep, such as the
          verses for a lesson or a hard week; a box appears under the results. Choose <em>A new list</em> and give it a
          name, or choose one of your lists to add to, and press <em>Save</em> (<em>Cancel</em> clears the ticks). An
          entry already in the list is not added twice. <em>Select all</em>, above the checkboxes, ticks every result
          of the search, including those on other pages or behind <em>Show more</em> (up to 200 at a time); in Search
          everything it ticks the results of every section.
        </p>
        <Screenshot
          name="list-save"
          width={1152}
          height={1000}
          alt="Bible search results for comfort with three ticked, and the box under them: Save in A new list, the name Comfort verses, Save and Cancel"
          caption="Three verses ticked and a new list named, ready to save."
        />
        <p>
          <PageLink onNavigate={onNavigate} view="lists">My lists</PageLink> (in the account icon's menu, under My notes)
          shows your lists. Choose one to see its entries as the search showed them (the search is not run again), each
          with a link to open it (<em>Read in the Bible</em>, <em>Read the note</em>, <em>Play this song</em> and so on)
          and <em>Remove from the list</em>. You can <em>Rename</em> a list or <em>Delete the list</em> (you are asked
          first). <em>Copy to notes</em> puts the whole list into one note, on its first verse, commentary note or
          reading, so you can add your own thoughts to it in My notes. Your lists are yours alone unless you share one.
        </p>
        <p>
          <em>Export all lists and playlists</em> (or <em>Export this list</em>, or <em>Export this playlist</em> on the
          Christian media page) saves them in a file on your computer, and <em>Import lists and playlists…</em> reads such
          a file back as new lists and playlists, here or on another copy of this site (one with a name you already use
          gets &ldquo;(copy)&rdquo; after it; a song that is not on this site is left out). If the site&rsquo;s administrators have allowed
          your account to share, <em>Share on Public lists</em> puts a list on{' '}
          <PageLink onNavigate={onNavigate} view="publicLists">Public lists</PageLink> (under Members), where everyone
          can see it with your first name and the first letter of your last name; <em>Stop sharing</em> takes it off.
          On Public lists, a logged-in member can <em>Copy to My lists</em>. Playlists of songs are shared the same
          way, from <em>Your playlists</em> on the Christian media page: a shared playlist is listed on Public lists
          too, where anyone can <em>Play</em> it, and <em>Copy link</em> gives an address to send to a friend.
        </p>
        <Screenshot
          name="public-lists"
          width={1152}
          height={1000}
          alt="Public lists: a list Verses for a hard week shared by Ruth C., with its four verses, and beside it a shared playlist Evening hymns"
          caption="Public lists: lists and playlists members chose to share with everyone."
        />
        <Screenshot
          name="my-lists"
          width={1152}
          height={1000}
          alt="My lists with the list Comfort verses open: its three verses, each with Read in the Bible and Remove from the list, and Rename, Delete the list and Copy to notes"
          caption="My lists, with a list open."
        />
      </section>

      <section id="help-conversations" tabIndex={-1} className="help-section">
        <h2>Conversations</h2>
        <p>
          Conversations is a place where members of the site write posts for one another and reply to them. Anyone can
          read and search it, with or without an account: <em>Conversations</em> is in the sidebar (under Members) and
          at the foot of the welcome page. Writing posts and replies is turned on for each account by hand, so to take
          part, set up an account, then use the <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> form
          to ask to join, giving the email address of your account. Once it is turned on, log in.
        </p>
        <ul className="welcome-tips">
          <li>
            <strong>Reading.</strong> The posts are listed newest first, ten to a page, each with its title, its
            author&rsquo;s name and when it was written. Anyone can read every post and its replies, so remember
            that what you write there, with your name, can be read by everyone.
          </li>
          <li>
            <strong>Writing.</strong> Press <em>Write a post</em>, give it a title, write in the box (with bold,
            italic, headings, lists, quotations and links; up to 20,000 characters) and press <em>Post it</em>. Your
            name is shown with it, never your email address. Tick <em>Email me replies</em> under the box (it starts
            unticked) to be emailed each new reply to that post; your address must be confirmed. Each email has a link
            to stop them, or edit the post and untick it.
          </li>
          <li>
            <strong>Sending a post to one member.</strong> Under the box, <em>Send to</em> starts on{' '}
            <em>Everyone</em>; choose a member instead (by name) and only the two of you see the post and its replies
            (and the site&rsquo;s administrators). The first time you send to someone, they are asked whether to accept
            posts from you, on the Conversations page and by email or text; your post says it is waiting until they
            do. If they accept, they are not asked again; if they decline, you cannot send them posts. Each of you is
            told of the other&rsquo;s replies.
          </li>
          <li>
            <strong>What not to post.</strong> Posts and replies should not contain profanity, political messages or
            advertising; the line above the <em>Post it</em> and <em>Post reply</em> buttons says so, and posting means
            you agree to the <PageLink onNavigate={onNavigate} view="postingPolicy">Posting policy</PageLink>. If the
            site&rsquo;s administrators have turned it on, each new or changed post and reply is first checked by an AI
            (Google Gemini); one it finds unsuitable is not saved, and you are told why so you can change it. Private
            prayer requests are never sent to it.
          </li>
          <li>
            <strong>When someone wants to send you posts.</strong> A box at the top of Conversations (and an email or
            text) shows the request: <em>Accept</em> shows their posts, <em>Decline</em> stops them. Change your answer
            any time under <em>Posts sent to you</em> on your Account settings page (<em>Allow</em> or{' '}
            <em>Block</em>).
          </li>
          <li>
            <strong>Changing or deleting.</strong> Your own posts have <em>Edit</em> and <em>Delete</em> (you are
            asked before one is deleted). Only you can change or delete them. Deleting a post also deletes its replies.
          </li>
          <li>
            <strong>Replying.</strong> Press <em>Reply</em> under any post, write in the box (up to 5,000 characters)
            and press <em>Post reply</em>. Replies are shown under the post, oldest first, with each author&rsquo;s
            name and the time. Your own replies have <em>Edit</em> and <em>Delete</em>.
          </li>
          <li>
            <strong>Searching.</strong> Type words in the search box to find the posts that have all of them in the
            title, the text, the author&rsquo;s name or a reply (the words are highlighted). Tick <em>Only my posts</em> to see
            just yours.
          </li>
        </ul>
        <Screenshot
          name="conversations"
          width={1152}
          height={1000}
          alt="The Conversations page with two posts by two members, one with a reply, and Edit and Delete on the member's own post"
          caption="Conversations: posts by members, newest first, with their replies, and Edit and Delete on your own."
        />
        <Screenshot
          name="send-to-member"
          width={1152}
          height={1150}
          alt="Write a post with Send to set to Ruth Carter only, the note that only the two of them will see it, the posting line, and a Send to Ruth Carter button"
          caption="Writing a post to one member: choose them under Send to."
        />
        <Screenshot
          name="message-request"
          width={1152}
          height={760}
          alt="Requests to send you posts at the top of Conversations: Daniel Brooks would like to send you posts, with Accept and Decline"
          caption="When another member first sends you a post, you choose whether to accept posts from them."
        />
      </section>

      <section id="help-prayer-wall" tabIndex={-1} className="help-section">
        <h2>Prayer Wall</h2>
        <p>
          The <PageLink onNavigate={onNavigate} view="prayerWall">Prayer Wall</PageLink> (in the sidebar under Members,
          below Conversations) is where members share prayer requests and praises, and others reply to say they are
          praying. It works exactly like Conversations: anyone can read and search it, and the members who may write in
          Conversations may write here too (press <em>Share a prayer request</em>). The two are kept apart: a prayer
          request shows only on the Prayer Wall, and a Conversations post only in Conversations. Anyone can read what
          you share, with your name, so leave out what others would not want made public.
        </p>
        <p>
          Under a request&rsquo;s text, <em>Who sees this request</em> offers one choice. <em>Public</em> (the usual)
          shows it to everyone with your name. <em>Post anonymously</em> shows &ldquo;Anonymous&rdquo; instead of your
          name. <em>Private</em> keeps the request off the Prayer Wall for everyone but you; the site owner and
          administrators can still read it, and it is sent to them (and nobody else) in their prayer list email.{' '}
          <em>Add to the prayer list email</em> sends it to everyone who gets the prayer list by email. If a church
          leader has added you to a group, there are two more for each group: <em>Email</em> and the group&rsquo;s name
          sends it at once to everyone in that group, and <em>Email</em>, the group&rsquo;s name and{' '}
          <em>leader</em> sends it to its leader only; either way it carries your name, replies come to your email
          address, and the request becomes private on the Prayer Wall. You can change the choice later with Edit (a
          group or leader chosen again is not emailed twice). When
          a prayer is answered, tick <em>Answered</em> beside Edit and Delete under your request (no need to edit it):
          everyone then sees it marked &ldquo;Answered&rdquo;, and it is left out of the prayer list emails.
        </p>
        <Screenshot
          name="prayer-wall"
          width={1152}
          height={900}
          alt="The Prayer Wall with prayer requests by members: one posted anonymously, one marked Answered, and one with a reply"
          caption="The Prayer Wall: prayer requests and praises, newest first, with replies; one posted anonymously and one marked Answered."
        />
        <Screenshot
          name="prayer-request-form"
          width={1152}
          height={1100}
          alt="Share a prayer request: a title, the text, and the Post anonymously, Private and Email this request to the prayer list choices"
          caption="Sharing a prayer request, with its three choices under the text."
        />
        <p>
          <strong>The prayer list by email:</strong> anyone with an account and a confirmed email address can open{' '}
          <em>Email me the prayer list each week</em> at the top of the Prayer Wall and choose a day, a time and a time
          zone. Once a week you get the requests members chose to email in the past week, leaving out answered ones (none
          is sent in a week with no new requests). It comes by email, by text (a short text with a link) or both, as you
          chose on My account. Each
          email has a link to stop them, or use <em>Stop the emails</em> in the same place.
        </p>
        <Screenshot
          name="prayer-list-email"
          width={828}
          height={517}
          alt="Email me the prayer list each week, open, with a day of the week, a time of day, a time zone and an Email it to me each week button"
          caption="Choosing a day and time to receive the prayer list each week."
        />
      </section>

      <section id="help-contact" tabIndex={-1} className="help-section">
        <h2>Contact</h2>
        <p>
          Use the <PageLink onNavigate={onNavigate} view="contact">Contact</PageLink> form for questions, corrections, suggestions, or to ask
          for something to be turned on for your account: your own FAQ questions (see{' '}
          <button type="button" className="link-button" onClick={() => goToSection('help-faq')}>
            FAQ
          </button>
          ), writing in Conversations and on the Prayer Wall, or your own pins, routes and notes on the maps. Give the
          email address of your account. Enter your name, your email address (so we can reply), a phone number if you like, and your message, and
          press <em>Send Message</em>. The form is protected from spam by Google reCAPTCHA, which works in the
          background: there is no box to tick. What the site keeps about you, and what it sends to other services, is
          on the <PageLink onNavigate={onNavigate} view="privacy">Privacy</PageLink> page.
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
          The Bibles you can read here, the commentaries, the devotionals and the other books are in the public domain
          (except the modern English wording of the Apostles’ Creed, whose credit is shown with it).
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
          ). The other Bibles, the commentaries, the devotionals and the other books are in the public domain (except the
          modern wording of the Apostles’ Creed).{hasMaps ? ' Maps from Biblica® Open Color Bible Maps™ (Biblica, Inc., CC BY-SA 4.0).' : ''} The full
          credits and notices are on the <PageLink onNavigate={onNavigate} view="copyright">Bible copyright notices</PageLink> page.
        </p>
      </section>
    </div>
  )
}

export default HelpPage
