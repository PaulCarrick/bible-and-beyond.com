import type { View } from './views'

interface TutorialPageProps {
  onNavigate: (view: View) => void
}

// The narrated tour of the site, a video of about ten minutes (remade 2026-11-12). The video file is too large for git: it lives in
// public/tutorial/ on the server only (see "Tutorial video" in CLAUDE.md). The poster and captions are committed.
function TutorialPage({ onNavigate }: TutorialPageProps) {
  return (
    <div className="welcome tutorial-page">
      <h1>Tutorial video</h1>
      <p>
        A ten-minute tour of Bible and Beyond: reading and searching the Bible, the commentaries, the devotionals,
        the other books and the music, searching the Internet Archive, the FAQ, and what a free account adds: notes,
        daily emails, playlists, and on request AI search, your own questions and Conversations. Press play to start;
        the button at the bottom right shows it full screen, and CC turns the captions on or off.
      </p>
      <video
        className="tutorial-video"
        controls
        preload="metadata"
        playsInline
        poster="/tutorial/poster.webp"
        width={1920}
        height={1080}
      >
        <source src="/tutorial/bible-and-beyond-feature-tour.mp4" type="video/mp4" />
        <track kind="captions" src="/tutorial/bible-and-beyond-feature-tour.en.vtt" srcLang="en" label="English" />
        Your browser cannot play this video.{' '}
        <a href="/tutorial/bible-and-beyond-feature-tour.mp4">Download it instead</a>.
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
