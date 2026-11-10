import { useEffect, useRef } from 'react'
import { musicFileAddress } from './api'
import type { MusicSong } from './api'
import MusicLicenceNote from './MusicLicenceNote'

interface MusicPageProps {
  songs: MusicSong[]
  isHidden: boolean
  // A song to show (from /music?song=..., or "Play this song" on the search page), with a new key each time.
  focus: { id: string; key: number } | null
}

// The Christian music section: one closed section per published song (its title and author), which opens to
// its player and its words, so a long list stays short. A link to a song opens its section. The players load
// nothing until a visitor presses play (preload none), so a long list costs no requests. Starting one pauses
// the others, and closing a section stops its song. The page stays mounted, so a song playing goes on while
// another page is open, except a video, which is paused when the page is left (it could not be seen).
function MusicPage({ songs, isHidden, focus }: MusicPageProps) {
  const listReference = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isHidden) {
      listReference.current?.querySelectorAll('video').forEach((video) => video.pause())
    }
  }, [isHidden])

  useEffect(() => {
    if (!focus || isHidden) {
      return
    }
    const element = document.getElementById(`song-${focus.id}`)
    if (element instanceof HTMLDetailsElement) {
      element.open = true
      element.scrollIntoView({ block: 'start' })
      element.querySelector('summary')?.focus({ preventScroll: true })
    }
  }, [focus, isHidden, songs])

  // Only one song at a time.
  function pauseTheOthers(playing: HTMLMediaElement) {
    listReference.current?.querySelectorAll<HTMLMediaElement>('audio, video').forEach((player) => {
      if (player !== playing) {
        player.pause()
      }
    })
  }

  return (
    <div className="welcome music-page" hidden={isHidden}>
      <h1>Christian music</h1>
      <p>Hymns and songs to listen to, with their words. Open a song to play it and read its words; only one plays at a time.</p>
      <div ref={listReference} className="music-list">
        {songs.map((song) => (
          <details
            key={song.id}
            id={`song-${song.id}`}
            className="music-song"
            onToggle={(event) => {
              if (!event.currentTarget.open) {
                event.currentTarget.querySelectorAll<HTMLMediaElement>('audio, video').forEach((player) => player.pause())
              }
            }}
          >
            <summary>
              <span className="music-title">{song.title}</span>
              {song.author && <span className="music-author">{song.author}</span>}
            </summary>
            <div className="music-body">
              {song.kind === 'video' ? (
                <video
                  className="music-video"
                  controls
                  preload="none"
                  playsInline
                  src={musicFileAddress(song)}
                  onPlay={(event) => pauseTheOthers(event.currentTarget)}
                >
                  Your browser cannot play this video.
                </video>
              ) : (
                <audio className="music-audio" controls preload="none" src={musicFileAddress(song)} onPlay={(event) => pauseTheOthers(event.currentTarget)}>
                  Your browser cannot play this recording.
                </audio>
              )}
              {song.lyrics && (
                <div className="music-lyrics">
                  {song.lyrics.split(/\n{2,}/).map((verse, index) => (
                    <p key={index}>{verse}</p>
                  ))}
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
      <p className="related-note music-licence">
        <MusicLicenceNote />
      </p>
    </div>
  )
}

export default MusicPage
