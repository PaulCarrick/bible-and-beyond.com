import type { View } from './views'

interface TutorialPageProps {
  onNavigate: (view: View) => void
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// The narrated tour of the site, a video of about fourteen minutes (remade 2026-11-24). The video file is too large for git: it lives in
// public/tutorial/ on the server only (see "Tutorial video" in CLAUDE.md). The poster and captions are committed.
function TutorialPage({ onNavigate, siteTitle }: TutorialPageProps) {
  return (
    <div className="welcome tutorial-page">
      <h1>Tutorial video</h1>
      <p>
        A fourteen-minute tour of {siteTitle}: reading and searching the Bible, the commentaries, the devotionals,
        the other books, the media and the maps, searching the Internet Archive, the FAQ, the verse and devotional of the
        day, and what a free account adds (set up with an email address or a cell phone number): notes, lists of search
        results, daily emails, a verse a day, text messages, playlists and Account settings (with your picture), and on request
        sharing lists on Public lists, AI search, your own questions, posting in Conversations (to everyone or one member)
        and on the Prayer Wall, and your own pins and routes on the maps. Press play to start;
        the button at the bottom right shows it full screen, and CC turns the captions on or off.
      </p>
      <video
        className="tutorial-video"
        controls
        preload="metadata"
        playsInline
        poster="/tutorial/poster.webp?v=2026-11-24"
        width={1920}
        height={1080}
      >
        <source src="/tutorial/bible-and-beyond-feature-tour.mp4?v=2026-11-24" type="video/mp4" />
        <track kind="captions" src="/tutorial/bible-and-beyond-feature-tour.en.vtt?v=2026-11-24" srcLang="en" label="English" />
        Your browser cannot play this video.{' '}
        <a href="/tutorial/bible-and-beyond-feature-tour.mp4?v=2026-11-24">Download it instead</a>.
      </video>
      <p>
        For more detail on any part of the site, with pictures, see the{' '}
        <button type="button" className="link-button" onClick={() => onNavigate('help')}>
          Help
        </button>{' '}
        page.
      </p>
    </div>
  )
}

export default TutorialPage
