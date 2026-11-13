import { useContext, useEffect, useRef, useState } from 'react'
import { deletePlaylist, fetchPlaylists, formattedHtmlForPage, musicFileAddress, musicWordsAddress, savePlaylist } from './api'
import type { MusicSong, Playlist } from './api'
import { AccountContext } from './AccountContext'
import MusicLicenceNote from './MusicLicenceNote'

interface MusicPageProps {
  songs: MusicSong[]
  isHidden: boolean
  // A song to show (from /music?song=..., or "Play this song" on the search page), with a new key each time.
  focus: { id: string; key: number } | null
}

// A playlist being played: its name and songs, and which one is playing.
interface PlayingList {
  name: string
  songIds: string[]
  index: number
}

// The Christian music section: one closed section per published song (its title and author), which opens to
// its player and its words (a PDF or picture of them when there is one, else the typed words), so a long list stays short. A link to a song opens its section. The players load
// nothing until a visitor presses play (preload none), so a long list costs no requests. Starting one pauses
// the others, and closing a section stops its song. The page stays mounted, so a song playing goes on while
// another page is open, except a video, which is paused when the page is left (it could not be seen).
//
// A logged-in visitor also gets a checkbox at the right of each song; once some are ticked, a box under the
// playlists (above the list) saves them under a name. Their playlists are in a closed section at the top of the page: choose one and Play
// plays its songs one after another, opening each and scrolling to it; a song's title in the list plays the
// playlist from that song; Reorder moves its songs up and down.
function MusicPage({ songs, isHidden, focus }: MusicPageProps) {
  const { user } = useContext(AccountContext)
  const listReference = useRef<HTMLDivElement>(null)
  const [tickedIds, setTickedIds] = useState<Set<string>>(new Set())
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [chosenPlaylistId, setChosenPlaylistId] = useState<number | null>(null)
  const [playlistName, setPlaylistName] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)
  const [isPlaylistsOpen, setIsPlaylistsOpen] = useState(false)
  // The chosen playlist's songs in the order being arranged, while Reorder is open.
  const [reorderIds, setReorderIds] = useState<string[] | null>(null)
  // What happened at the top (the playlists) and at the foot (saving the ticked songs).
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [saveErrorMessage, setSaveErrorMessage] = useState('')
  const [playing, setPlaying] = useState<PlayingList | null>(null)
  // The playlist being played, for the players' own events (which see the state of the render they were made in).
  const playingReference = useRef<PlayingList | null>(null)
  const userId = user?.id ?? null

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

  // Nothing of the last visitor's stays after logging out or in as someone else (reset while rendering, as
  // React advises for state that follows a prop).
  const [shownUserId, setShownUserId] = useState(userId)
  if (shownUserId !== userId) {
    setShownUserId(userId)
    setTickedIds(new Set())
    setPlaylists([])
    setChosenPlaylistId(null)
    setPlaylistName('')
    setReorderIds(null)
    setIsConfirmingDelete(false)
    setMessage('')
    setErrorMessage('')
    setSaveMessage('')
    setSaveErrorMessage('')
    setPlaying(null)
  }

  // The players' events read the playlist being played from here.
  useEffect(() => {
    playingReference.current = playing
  }, [playing])

  // The visitor's playlists, whenever someone logs in.
  useEffect(() => {
    if (userId === null) {
      return
    }
    const controller = new AbortController()
    fetchPlaylists(controller.signal)
      .then((loaded) => {
        setPlaylists(loaded)
        setChosenPlaylistId(loaded[0]?.id ?? null)
      })
      .catch((error: Error) => {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId])

  // Changes the playlist being played at once, for an event that comes before the next render.
  function changePlaying(next: PlayingList | null) {
    playingReference.current = next
    setPlaying(next)
  }

  // Only one song at a time. A song started by hand that is not the playlist's ends the playlist.
  function handlePlay(playing: HTMLMediaElement, songId: string) {
    listReference.current?.querySelectorAll<HTMLMediaElement>('audio, video').forEach((player) => {
      if (player !== playing) {
        player.pause()
      }
    })
    const list = playingReference.current
    if (list && list.songIds[list.index] !== songId) {
      changePlaying(null)
    }
  }

  // Opens a song, scrolls to it and starts it. Some browsers (on phones especially) refuse to start a song
  // that the visitor did not press play on; the song is then open and in view, ready for a tap.
  function startSong(songId: string) {
    const element = document.getElementById(`song-${songId}`)
    if (!(element instanceof HTMLDetailsElement)) {
      return
    }
    element.open = true
    element.scrollIntoView({ block: 'start', behavior: 'smooth' })
    const player = element.querySelector<HTMLMediaElement>('audio, video')
    player?.play().catch(() => setMessage('Press play on the song to go on with the playlist.'))
  }

  function handleEnded(songId: string) {
    const list = playingReference.current
    if (!list || list.songIds[list.index] !== songId) {
      return
    }
    const nextIndex = list.index + 1
    const previous = document.getElementById(`song-${songId}`)
    if (previous instanceof HTMLDetailsElement) {
      previous.open = false
    }
    if (nextIndex >= list.songIds.length) {
      changePlaying(null)
      setMessage(`The playlist “${list.name}” has finished.`)
      return
    }
    changePlaying({ ...list, index: nextIndex })
    startSong(list.songIds[nextIndex])
  }

  const songsById = new Map(songs.map((song) => [song.id, song]))
  const chosenPlaylist = playlists.find((playlist) => playlist.id === chosenPlaylistId) ?? null
  // Only the songs on the page now (a song hidden since the list was loaded is skipped).
  const chosenSongs = chosenPlaylist ? chosenPlaylist.song_ids.filter((id) => songsById.has(id)) : []
  const tickedSongs = songs.filter((song) => tickedIds.has(song.id))
  const trimmedName = playlistName.trim().replace(/\s+/g, ' ')
  const nameInUse = playlists.some((playlist) => playlist.name.toLowerCase() === trimmedName.toLowerCase())

  function toggleTick(songId: string, isTicked: boolean) {
    setTickedIds((current) => {
      const next = new Set(current)
      if (isTicked) {
        next.add(songId)
      } else {
        next.delete(songId)
      }
      return next
    })
  }

  // Puts a saved playlist in the list (by name) and chooses it.
  function keepPlaylist(playlist: Playlist) {
    setPlaylists((current) =>
      [...current.filter((entry) => entry.id !== playlist.id), playlist].sort((first, second) =>
        first.name.localeCompare(second.name, undefined, { sensitivity: 'base' }),
      ),
    )
    setChosenPlaylistId(playlist.id)
  }

  // Saves the ticked songs. Replacing a playlist keeps the order of the songs it already had; songs newly
  // ticked go at the end, in the order of the page.
  async function handleSave() {
    setIsBusy(true)
    setSaveMessage('')
    setSaveErrorMessage('')
    const existing = playlists.find((playlist) => playlist.name.toLowerCase() === trimmedName.toLowerCase())
    const kept = existing ? existing.song_ids.filter((id) => tickedIds.has(id) && songsById.has(id)) : []
    const added = tickedSongs.map((song) => song.id).filter((id) => !kept.includes(id))
    try {
      const { playlist, replaced } = await savePlaylist(trimmedName, [...kept, ...added])
      keepPlaylist(playlist)
      setReorderIds(null)
      setMessage('')
      setTickedIds(new Set())
      setPlaylistName('')
      const count = playlist.song_ids.length
      setSaveMessage(
        `${replaced ? 'Replaced' : 'Saved'} the playlist “${playlist.name}” (${count} ${count === 1 ? 'song' : 'songs'}). ` +
          'Open Your playlists above to play it.',
      )
    } catch (error) {
      setSaveErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  // Plays the chosen playlist from one of its songs (the first unless said) to the end.
  function handlePlayPlaylist(startIndex = 0) {
    if (!chosenPlaylist || chosenSongs.length === 0) {
      return
    }
    setMessage('')
    setErrorMessage('')
    changePlaying({ name: chosenPlaylist.name, songIds: chosenSongs, index: startIndex })
    startSong(chosenSongs[startIndex])
  }

  function handleReorder() {
    setMessage('')
    setErrorMessage('')
    setIsConfirmingDelete(false)
    setReorderIds(chosenSongs)
  }

  // Moves a song one place up (-1) or down (+1). At either end it stays (the button keeps the focus).
  function moveSong(index: number, step: number) {
    setReorderIds((current) => {
      if (!current || index + step < 0 || index + step >= current.length) {
        return current
      }
      const next = [...current]
      ;[next[index], next[index + step]] = [next[index + step], next[index]]
      return next
    })
  }

  async function handleSaveOrder() {
    if (!chosenPlaylist || !reorderIds) {
      return
    }
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    try {
      const { playlist } = await savePlaylist(chosenPlaylist.name, reorderIds)
      keepPlaylist(playlist)
      setReorderIds(null)
      setMessage(`Saved the new order of “${playlist.name}”.`)
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  function handleStop() {
    const list = playingReference.current
    if (list) {
      const element = document.getElementById(`song-${list.songIds[list.index]}`)
      element?.querySelector<HTMLMediaElement>('audio, video')?.pause()
    }
    changePlaying(null)
  }

  // Ticks the playlist's songs and puts its name in the box, so it can be changed and saved again.
  function handleChange() {
    if (!chosenPlaylist) {
      return
    }
    setTickedIds(new Set(chosenSongs))
    setPlaylistName(chosenPlaylist.name)
    setSaveMessage('')
    setSaveErrorMessage('')
    setMessage(
      `The songs of “${chosenPlaylist.name}” are ticked. Change the ticks in the list, then save it again under Your playlists (its order is kept).`,
    )
  }

  async function handleDelete() {
    if (!chosenPlaylist) {
      return
    }
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    try {
      await deletePlaylist(chosenPlaylist.id)
      const remaining = playlists.filter((playlist) => playlist.id !== chosenPlaylist.id)
      setPlaylists(remaining)
      setChosenPlaylistId(remaining[0]?.id ?? null)
      setMessage(`Deleted the playlist “${chosenPlaylist.name}”.`)
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
      setIsConfirmingDelete(false)
    }
  }

  const playingSong = playing ? songsById.get(playing.songIds[playing.index]) : undefined

  return (
    <div className="welcome music-page" hidden={isHidden}>
      <h1>Christian media</h1>
      <p>Hymns and songs to listen to, with their words. Open a song to play it and read its words; only one plays at a time.</p>
      {user && songs.length > 0 && (
        <details
          className="music-playlists"
          open={isPlaylistsOpen}
          onToggle={(event) => setIsPlaylistsOpen(event.currentTarget.open)}
        >
          <summary>
            Your playlists{playlists.length > 0 ? ` (${playlists.length})` : ''}
            {playing && playingSong && <span className="music-playlists-playing"> · playing “{playing.name}”</span>}
          </summary>
          <div className="music-playlists-body">
            {playlists.length === 0 ? (
              <p>You have no playlists yet. Tick the songs you want in the list below; a box to name and save the playlist then appears here.</p>
            ) : (
              <div className="music-playlist-play">
                <label>
                  Playlist
                  <select
                    value={chosenPlaylistId ?? ''}
                    disabled={reorderIds !== null}
                    onChange={(event) => {
                      setChosenPlaylistId(Number(event.target.value))
                      setIsConfirmingDelete(false)
                    }}
                  >
                    {playlists.map((playlist) => (
                      <option key={playlist.id} value={playlist.id}>
                        {playlist.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="primary-button"
                  disabled={chosenSongs.length === 0 || reorderIds !== null}
                  onClick={() => handlePlayPlaylist()}
                >
                  Play
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={chosenSongs.length < 2 || reorderIds !== null}
                  onClick={handleReorder}
                >
                  Reorder
                </button>
                {playing && (
                  <button type="button" className="secondary-button" onClick={handleStop}>
                    Stop
                  </button>
                )}
              </div>
            )}

            {playing && playingSong && (
              <p className="music-now-playing" role="status">
                Playing “{playing.name}”: song {playing.index + 1} of {playing.songIds.length}, <strong>{playingSong.title}</strong>
              </p>
            )}

            {chosenPlaylist && reorderIds && (
              <div className="music-playlist-songs">
                <p className="music-playlist-hint">Move the songs with the arrows, then save the order.</p>
                <ol className="music-reorder-list">
                  {reorderIds.map((id, index) => {
                    const title = songsById.get(id)?.title ?? id
                    return (
                      <li key={id}>
                        <span className="music-reorder-title">{title}</span>
                        <button
                          type="button"
                          className="secondary-button small-button"
                          aria-label={`Move ${title} up`}
                          title="Move up"
                          aria-disabled={index === 0}
                          onClick={() => moveSong(index, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="secondary-button small-button"
                          aria-label={`Move ${title} down`}
                          title="Move down"
                          aria-disabled={index === reorderIds.length - 1}
                          onClick={() => moveSong(index, 1)}
                        >
                          ↓
                        </button>
                      </li>
                    )
                  })}
                </ol>
                <div className="music-reorder-actions">
                  <button type="button" className="primary-button" disabled={isBusy} onClick={handleSaveOrder}>
                    Save order
                  </button>
                  <button type="button" className="secondary-button" disabled={isBusy} onClick={() => setReorderIds(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {chosenPlaylist && !reorderIds && (
              <div className="music-playlist-songs">
                {chosenSongs.length === 0 ? (
                  <p>This playlist has no songs on the site now.</p>
                ) : (
                  <>
                    <p className="music-playlist-hint">Click a song to play the playlist from there.</p>
                    <ol>
                      {chosenSongs.map((id, index) => (
                        <li key={id}>
                          <button
                            type="button"
                            className={
                              playing && playing.songIds[playing.index] === id ? 'link-button music-playlist-song playing' : 'link-button music-playlist-song'
                            }
                            title="Play the playlist from this song"
                            onClick={() => handlePlayPlaylist(index)}
                          >
                            {songsById.get(id)?.title}
                          </button>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
                <div className="note-actions">
                  <button type="button" className="link-button" onClick={handleChange}>
                    Change this playlist
                  </button>
                  {isConfirmingDelete ? (
                    <>
                      <span>Delete “{chosenPlaylist.name}”?</span>
                      <button type="button" className="link-button danger" disabled={isBusy} onClick={handleDelete}>
                        Yes, delete it
                      </button>
                      <button type="button" className="link-button" onClick={() => setIsConfirmingDelete(false)}>
                        No
                      </button>
                    </>
                  ) : (
                    <button type="button" className="link-button danger" onClick={() => setIsConfirmingDelete(true)}>
                      Delete this playlist
                    </button>
                  )}
                </div>
              </div>
            )}

            {message && <p role="status">{message}</p>}
            {errorMessage && (
              <p className="error" role="alert">
                {errorMessage}
              </p>
            )}
          </div>
        </details>
      )}
      {user && tickedSongs.length > 0 && (
        <section className="music-playlist-save" aria-label="Save the ticked songs as a playlist">
          <p>
            {tickedSongs.length} {tickedSongs.length === 1 ? 'song' : 'songs'} ticked.
          </p>
          <label>
            Playlist name
            <input
              type="text"
              value={playlistName}
              maxLength={100}
              onChange={(event) => setPlaylistName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && trimmedName && !isBusy) {
                  handleSave()
                }
              }}
            />
          </label>
          <button type="button" className="primary-button" disabled={isBusy || !trimmedName} onClick={handleSave}>
            {nameInUse ? 'Replace the playlist' : 'Save as a playlist'}
          </button>
          <button type="button" className="secondary-button" onClick={() => setTickedIds(new Set())}>
            Clear the ticks
          </button>
          {nameInUse && (
            <p className="music-playlist-hint">
              You already have a playlist called “{trimmedName}”; saving replaces its songs (keeping their order).
            </p>
          )}
        </section>
      )}
      {user && (saveMessage || saveErrorMessage) && (
        <div className="music-save-messages">
          {saveMessage && <p role="status">{saveMessage}</p>}
          {saveErrorMessage && (
            <p className="error" role="alert">
              {saveErrorMessage}
            </p>
          )}
        </div>
      )}

      {user && songs.length > 0 && (
        <p className="music-tick-heading">Tick songs for a playlist</p>
      )}
      <div ref={listReference} className={user ? 'music-list with-ticks' : 'music-list'}>
        {songs.map((song) => (
          <div key={song.id} className="music-row">
            <details
              id={`song-${song.id}`}
              className={playingSong?.id === song.id ? 'music-song playing' : 'music-song'}
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
                    onPlay={(event) => handlePlay(event.currentTarget, song.id)}
                    onEnded={() => handleEnded(song.id)}
                  >
                    Your browser cannot play this video.
                  </video>
                ) : (
                  <audio
                    className="music-audio"
                    controls
                    preload="none"
                    src={musicFileAddress(song)}
                    onPlay={(event) => handlePlay(event.currentTarget, song.id)}
                    onEnded={() => handleEnded(song.id)}
                  >
                    Your browser cannot play this recording.
                  </audio>
                )}
                {/* The words file when there is one (it loads only once the song is opened), else the typed words. */}
                {song.words_kind === 'image' && (
                  <img className="music-words-image" src={musicWordsAddress(song)} alt={`The words of ${song.title}`} loading="lazy" />
                )}
                {song.words_kind === 'pdf' && (
                  <div className="music-words-pdf">
                    <iframe src={musicWordsAddress(song)} title={`The words of ${song.title} (PDF)`} loading="lazy" />
                    {/* Some phones cannot show a PDF inside a page. */}
                    <a href={musicWordsAddress(song)} target="_blank" rel="noopener">
                      Open the words (PDF) in a new tab
                    </a>
                  </div>
                )}
                {!song.words_kind && song.lyrics_html && (
                  // The words from a PDF or Word document, with their formatting (cleaned by the server).
                  <div className="music-lyrics formatted-text" dangerouslySetInnerHTML={{ __html: formattedHtmlForPage(song.lyrics_html) }} />
                )}
                {!song.words_kind && !song.lyrics_html && song.lyrics && (
                  <div className="music-lyrics">
                    {song.lyrics.split(/\n{2,}/).map((verse, index) => (
                      <p key={index}>{verse}</p>
                    ))}
                  </div>
                )}
              </div>
            </details>
            {user && (
              <input
                type="checkbox"
                className="music-tick"
                checked={tickedIds.has(song.id)}
                onChange={(event) => toggleTick(song.id, event.target.checked)}
                aria-label={`Add ${song.title} to a playlist`}
                title="Tick to add this song to a playlist"
              />
            )}
          </div>
        ))}
      </div>

      <p className="related-note music-licence">
        <MusicLicenceNote />
      </p>
    </div>
  )
}

export default MusicPage
