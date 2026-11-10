import { useEffect, useRef } from 'react'
import { musicFileAddress } from './api'
import type { MusicSong } from './api'

interface MusicPageProps {
  songs: MusicSong[]
  isHidden: boolean
  // A song to show (from /music?song=..., or "Play this song" on the search page), with a new key each time.
  focus: { id: string; key: number } | null
}

// The Christian music section: each published song with its player and its words. The players load nothing
// until a visitor presses play (preload none), so a long list costs no requests. Starting one pauses the
// others. The page stays mounted, so a song playing goes on while another page is open, except a video,
// which is paused when the page is left (it could not be seen).
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
    element?.scrollIntoView({ block: 'start' })
    element?.focus({ preventScroll: true })
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
      <p>Hymns and songs to listen to, with their words. Press play on a song; only one plays at a time.</p>
      {songs.length > 3 && (
        <nav className="music-contents" aria-label="Songs">
          {/* Buttons, not #links: a # address would add a history entry the site's Back button does not expect. */}
          {songs.map((song) => (
            <button
              key={song.id}
              type="button"
              className="link-button"
              onClick={() => {
                const element = document.getElementById(`song-${song.id}`)
                element?.scrollIntoView({ block: 'start' })
                element?.focus({ preventScroll: true })
              }}
            >
              {song.title}
            </button>
          ))}
        </nav>
      )}
      <div ref={listReference}>
        {songs.map((song) => (
          <section key={song.id} id={`song-${song.id}`} className="music-song" tabIndex={-1} aria-labelledby={`song-title-${song.id}`}>
            <h2 id={`song-title-${song.id}`}>{song.title}</h2>
            {song.author && <p className="music-author">{song.author}</p>}
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
          </section>
        ))}
      </div>
    </div>
  )
}

export default MusicPage
