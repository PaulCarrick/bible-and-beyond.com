import { siteMedia } from './siteMedia'
import type { View } from './views'

interface TutorialPageProps {
  onNavigate: (view: View) => void
  // The site's name as this domain shows it (Site settings, or domainTitle.ts).
  siteTitle: string
}

// The narrated tour of the site, a video of about sixteen minutes (remade 2026-11-28). A site with a tour of its own
// (cr.orcas.church) gets its own files and words from siteMedia.ts. The video files are too large for git: they live
// in public/tutorial/ on each server only (see "Tutorial video" in CLAUDE.md). The posters and captions are committed.
function TutorialPage({ onNavigate, siteTitle }: TutorialPageProps) {
  const media = siteMedia()
  const video = `/tutorial/${media.tutorial}.mp4?v=${media.version}`
  return (
    <div className="welcome tutorial-page">
      <h1>Tutorial video</h1>
      <p>
        {media.description ?? (
          <>
            A sixteen-minute tour of {siteTitle}: reading, searching and listening to the Bible, the commentaries, the
            devotionals, the other books, the media and the maps, searching the Internet Archive, the FAQ, the verse and
            devotional of the day and making your own verse cards, and what a free account adds (set up with an email
            address or a cell phone number): notes, lists of search results, daily emails, a verse a day, text messages,
            playlists, My cards, My scheduled tasks and Account settings (with your picture), and on request sharing lists
            on Public lists, AI search, your own questions, posting in Conversations (to everyone or one member) and on the
            Prayer Wall, and your own pins and routes on the maps.
          </>
        )}{' '}
        Press play to start; the button at the bottom right shows it full screen, and CC turns the captions on or off.
      </p>
      <video
        className="tutorial-video"
        controls
        preload="metadata"
        playsInline
        poster={`/tutorial/${media.poster}.webp?v=${media.version}`}
        width={1920}
        height={1080}
      >
        <source src={video} type="video/mp4" />
        <track kind="captions" src={`/tutorial/${media.tutorial}.en.vtt?v=${media.version}`} srcLang="en" label="English" />
        Your browser cannot play this video.{' '}
        <a href={video}>Download it instead</a>.
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
