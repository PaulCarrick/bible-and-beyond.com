// Several sites are served from this same code (see "Tutorial video" in CLAUDE.md). A site listed here has Help
// pictures and a tutorial video of its own, taken from its own content: cr.orcas.church (2026-11-28), whose server
// deploys this repository. Every other site uses the pictures in public/help/ and the tour in public/tutorial/.
// The tutorial MP4s are not in git: each server has its own copy (copied by hand), under the file name given here.
export interface SiteMedia {
  // Where the Help page's pictures are, with no slash at the end.
  helpFolder: string
  // The tutorial's file names in public/tutorial/, without ".mp4", ".en.vtt" or "-poster.webp".
  tutorial: string
  poster: string
  // Its version, added to the addresses so a new one is fetched.
  version: string
  // What the Tutorial page says about it; null for the main site's own wording.
  description: string | null
}

const mainSite: SiteMedia = {
  helpFolder: '/help',
  tutorial: 'bible-and-beyond-feature-tour',
  poster: 'poster',
  version: '2026-11-28',
  description: null,
}

const ownMedia: Record<string, SiteMedia> = {
  'cr.orcas.church': {
    helpFolder: '/help/cr',
    tutorial: 'cr-feature-tour',
    poster: 'cr-poster',
    version: '2026-11-28',
    description:
      'An eleven-minute tour of this site: logging in, reading, searching and listening to the Bible, the devotionals, ' +
      'the Celebrate Recovery lessons and guides, the lesson videos, testimonies and songs, the FAQ, the verse and ' +
      'devotional of the day and making your own verse cards, and your account: your picture, notes, lists of search ' +
      'results, daily emails and texts, playlists, My cards, My scheduled tasks, Conversations and the Prayer Wall.',
  },
}

// This site's pictures and tutorial ("www." is ignored).
export function siteMedia(hostname: string = window.location.hostname): SiteMedia {
  return ownMedia[hostname.toLowerCase().replace(/^www\./, '')] ?? mainSite
}
