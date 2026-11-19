import type { SavedListEntry } from './api'

// The words of each kind of list entry's link, as in the searches (My lists and Public lists).
export const openWords: Record<SavedListEntry['kind'], string> = {
  bible: 'Read in the Bible',
  commentary: 'Read the note',
  devotional: 'Read this reading',
  book: 'Read this chapter',
  music: 'Play this song',
  map: 'Open this map',
  faq: 'Show the answer',
}
