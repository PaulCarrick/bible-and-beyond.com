import type { CommentarySource, DevotionalInfo, Translation } from './types'
import type { View } from './views'

// "A, B and C"
function joinList(items: string[]) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

interface WelcomePageProps {
  siteTitle: string
  translations: Translation[]
  commentaries: CommentarySource[]
  devotionals: DevotionalInfo[]
  onNavigate: (view: View) => void
}

// The page the site opens on: what it is and what is in it. How to use it, and where the texts come from, are on
// the Help page.
function WelcomePage({ siteTitle, translations, commentaries, devotionals, onNavigate }: WelcomePageProps) {
  const bibles = translations.filter((translation) => translation.source === 'local').map((translation) => translation.code)
  const licensed = translations
    .filter((translation) => translation.source === 'api_bible')
    .map((translation) => (translation.code === 'MSG' ? 'The Message' : translation.code))

  return (
    <div className="welcome">
      <h1>Welcome to {siteTitle}</h1>
      <p className="welcome-lead">
        {siteTitle} is a free, non-commercial site for reading and studying the Bible. It brings together
        public-domain Bibles, the Hebrew and Greek behind the English, cross references, classic commentaries and
        devotional books, so that from a single verse you can see what it says in the original languages, what other
        verses it points to, and what great teachers have written about it.
      </p>

      <h2>What you can do</h2>
      <div className="welcome-cards">
        <section className="welcome-card">
          <h3>The Bible</h3>
          <p>
            Read a chapter at a time in {bibles.length > 0 ? joinList(bibles) : 'the Bibles on this site'}, scrolling on
            from chapter to chapter and book to book, or search for words, phrases or a Strong&rsquo;s number such as{' '}
            <code>G0025</code> to find every verse that uses one Hebrew or Greek word.
            {licensed.length > 0 ? ` The ${joinList(licensed)} can be searched too.` : ''}
          </p>
          <div className="welcome-buttons">
            <button type="button" className="primary-button" onClick={() => onNavigate('read')}>
              Read the Bible
            </button>
            <button type="button" className="primary-button" onClick={() => onNavigate('bible')}>
              Search the Bible
            </button>
          </div>
        </section>
        {commentaries.length > 0 && (
          <section className="welcome-card">
            <h3>Commentaries</h3>
            <p>
              Search the text of {joinList(commentaries.map((entry) => entry.short_name))}, or choose a commentary and a
              verse and read on from there, chapter after chapter.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('commentary')}>
                Search the commentaries
              </button>
              <button type="button" className="primary-button" onClick={() => onNavigate('browse')}>
                Browse the commentaries
              </button>
            </div>
          </section>
        )}
        {devotionals.length > 0 && (
          <section className="welcome-card">
            <h3>Devotionals</h3>
            <p>
              Daily readings for every day of the year, opening at today&rsquo;s date, and two short classics of the
              devotional life: {joinList(devotionals.map((entry) => entry.name))}. With an account, any of them can be
              emailed to you each day at a time you choose.
            </p>
            <div className="welcome-buttons">
              <button type="button" className="primary-button" onClick={() => onNavigate('devotionals')}>
                Open the devotionals
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export default WelcomePage
