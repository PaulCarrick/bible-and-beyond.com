import { useContext, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { deletePlaylist, exportLists, fetchPlaylists, formattedHtmlForPage, musicFileAddress, musicWordsAddress, savePlaylist, sharedPlaylistAddress, sharePlaylist } from './api'
import PlaylistSaveBox from './PlaylistSaveBox'
import type { MusicSong, Playlist } from './api'
import { AccountContext } from './AccountContext'
import MusicLicenceNote from './MusicLicenceNote'

interface MusicPageProps {
  songs: MusicSong[]
  isHidden: boolean
  // A song to show (from /music?song=..., or "Play this song" on the search page), with a new key each time.
  focus: { id: string; key: number } | null
  // A playlist to play now (Play on Public lists, a shared playlist), with a new key each time.
  playRequest: { name: string; songIds: string[]; key: number } | null
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
// playlist from that song; Edit moves its songs up and down, removes some and adds others (chosen in a list).
function MusicPage({ songs, isHidden, focus, playRequest }: MusicPageProps) {
  const { user } = useContext(AccountContext)
  const listReference = useRef<HTMLDivElement>(null)
  // Edit's list of songs, for dragging: the song being dragged by its handle, if any.
  const editListReference = useRef<HTMLOListElement>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [tickedIds, setTickedIds] = useState<Set<string>>(new Set())
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [chosenPlaylistId, setChosenPlaylistId] = useState<number | null>(null)
  const [playlistName, setPlaylistName] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)
  const [isPlaylistsOpen, setIsPlaylistsOpen] = useState(false)
  // The chosen playlist's songs as they are being edited (order, removed, added), while Edit is open.
  const [editIds, setEditIds] = useState<string[] | null>(null)
  // What happened at the top (the playlists) and at the foot (saving the ticked songs).
  // The songs chosen in Edit's "Add songs" list, not yet added.
  const [songsToAdd, setSongsToAdd] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [playing, setPlaying] = useState<PlayingList | null>(null)
  // The playlist being played, for the players' own events (which see the state of the render they were made in).
  const playingReference = useRef<PlayingList | null>(null)
  // The last shared playlist started from Public lists, so it is not started again when the page is shown again.
  const playedRequestKey = useRef<number | null>(null)
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
    setEditIds(null)
    setIsConfirmingDelete(false)
    setMessage('')
    setErrorMessage('')
    setPlaying(null)
  }

  // The players' events read the playlist being played from here.
  useEffect(() => {
    playingReference.current = playing
  }, [playing])

  // The visitor's playlists, whenever someone logs in and each time the page is opened (one may have been
  // saved from the music search meanwhile). The playlist chosen stays chosen while it exists.
  useEffect(() => {
    if (userId === null || isHidden) {
      return
    }
    const controller = new AbortController()
    fetchPlaylists(controller.signal)
      .then((loaded) => {
        setPlaylists(loaded)
        setChosenPlaylistId((current) => (loaded.some((playlist) => playlist.id === current) ? current : loaded[0]?.id ?? null))
      })
      .catch((error: Error) => {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message)
        }
      })
    return () => controller.abort()
  }, [userId, isHidden])

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

  function handleEdit() {
    setMessage('')
    setErrorMessage('')
    setIsConfirmingDelete(false)
    setSongsToAdd([])
    setEditIds(chosenSongs)
  }

  // Dragging a song by its handle (mouse, pen or finger: pointer events, so it works on phones too). While a drag
  // is on, the window follows the pointer (not the handle: moving the row in the list can make the browser drop the
  // handle's hold on the pointer), and the song is moved to the place of the row under the pointer as it goes, so
  // the list shows where it will land. Letting go anywhere ends it.
  function startDrag(event: ReactPointerEvent<HTMLElement>, songId: string) {
    if (event.button !== 0) {
      return
    }
    event.preventDefault()
    setDraggingId(songId)
  }

  useEffect(() => {
    if (draggingId === null) {
      return
    }
    const follow = (event: PointerEvent) => {
      const list = editListReference.current
      if (!list) {
        return
      }
      event.preventDefault()
      const rows = [...list.querySelectorAll<HTMLLIElement>(':scope > li')]
      // The first row whose middle is below the pointer is where the song goes; past them all, the end.
      let target = rows.findIndex((row) => {
        const box = row.getBoundingClientRect()
        return event.clientY < box.top + box.height / 2
      })
      if (target === -1) {
        target = rows.length - 1
      }
      setEditIds((current) => {
        if (!current) {
          return current
        }
        const from = current.indexOf(draggingId)
        if (from === -1 || from === target) {
          return current
        }
        const next = current.filter((id) => id !== draggingId)
        next.splice(target, 0, draggingId)
        return next
      })
    }
    const stop = () => setDraggingId(null)
    window.addEventListener('pointermove', follow)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', follow)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [draggingId])

  function removeSong(index: number) {
    setEditIds((current) => (current ? current.filter((_, position) => position !== index) : current))
  }

  // Puts the songs chosen in the list at the end, in the order of the page.
  function addChosenSongs() {
    setEditIds((current) => {
      if (!current) {
        return current
      }
      const chosen = new Set(songsToAdd)
      return [...current, ...songs.filter((song) => chosen.has(song.id) && !current.includes(song.id)).map((song) => song.id)]
    })
    setSongsToAdd([])
  }

  // Moves a song one place up (-1) or down (+1). At either end it stays (the button keeps the focus).
  function moveSong(index: number, step: number) {
    setEditIds((current) => {
      if (!current || index + step < 0 || index + step >= current.length) {
        return current
      }
      const next = [...current]
      ;[next[index], next[index + step]] = [next[index + step], next[index]]
      return next
    })
  }

  async function handleSaveEdit() {
    if (!chosenPlaylist || !editIds || editIds.length === 0) {
      return
    }
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    try {
      const { playlist } = await savePlaylist(chosenPlaylist.name, editIds)
      keepPlaylist(playlist)
      setEditIds(null)
      setMessage(`Saved the changes to “${playlist.name}”.`)
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

  // A shared playlist from Public lists: played from its first song once the page is shown and its songs are loaded.
  useEffect(() => {
    if (!playRequest || isHidden || songs.length === 0 || playedRequestKey.current === playRequest.key) {
      return
    }
    // Just after the page is shown, so the first song's section can be opened and scrolled to.
    const timer = window.setTimeout(() => {
      playedRequestKey.current = playRequest.key
      const playable = playRequest.songIds.filter((id) => songs.some((song) => song.id === id))
      if (playable.length === 0) {
        setMessage(`None of the songs of “${playRequest.name}” are on the site now.`)
        return
      }
      setMessage('')
      setErrorMessage('')
      changePlaying({ name: playRequest.name, songIds: playable, index: 0 })
      startSong(playable[0])
    }, 0)
    return () => window.clearTimeout(timer)
  }, [playRequest, isHidden, songs])

  async function handleShare() {
    if (!chosenPlaylist) {
      return
    }
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    try {
      const changed = await sharePlaylist(chosenPlaylist.id, !chosenPlaylist.shared)
      setPlaylists((current) => current.map((playlist) => (playlist.id === changed.id ? { ...playlist, shared: changed.shared } : playlist)))
      setMessage(
        changed.shared
          ? `“${changed.name}” is now on Public lists, for everyone to see and play. Copy link gives you its address to send.`
          : `“${changed.name}” is no longer shared.`,
      )
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  async function handleExport() {
    if (!chosenPlaylist) {
      return
    }
    setMessage('')
    setErrorMessage('')
    try {
      await exportLists(undefined, chosenPlaylist.id)
      setMessage(`Saved “${chosenPlaylist.name}” in a file. Import it on My lists, here or on another copy of this site.`)
    } catch (error) {
      setErrorMessage((error as Error).message)
    }
  }

  async function handleCopyLink() {
    if (!chosenPlaylist) {
      return
    }
    const address = sharedPlaylistAddress(chosenPlaylist.id)
    try {
      await navigator.clipboard.writeText(address)
      setMessage(`Copied the link to “${chosenPlaylist.name}”: ${address}`)
    } catch {
      setMessage(`The link to “${chosenPlaylist.name}” is ${address}`)
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
                    disabled={editIds !== null}
                    onChange={(event) => {
                      setChosenPlaylistId(Number(event.target.value))
                      setIsConfirmingDelete(false)
                    }}
                  >
                    {playlists.map((playlist) => (
                      <option key={playlist.id} value={playlist.id}>
                        {playlist.name}
                        {playlist.shared ? ' · shared' : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="primary-button"
                  disabled={chosenSongs.length === 0 || editIds !== null}
                  onClick={() => handlePlayPlaylist()}
                >
                  Play
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={editIds !== null}
                  onClick={handleEdit}
                >
                  Edit
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

            {chosenPlaylist && editIds && (
              <div className="music-playlist-songs">
                <p className="music-playlist-hint">Drag the songs by ⠿ (or move them with the arrows), remove the ones you do not want, add others below, then save the changes.</p>
                {editIds.length === 0 && <p>No songs are left. Add some, or cancel and delete the playlist instead.</p>}
                <ol className="music-reorder-list" ref={editListReference}>
                  {editIds.map((id, index) => {
                    const title = songsById.get(id)?.title ?? id
                    return (
                      <li key={id} className={draggingId === id ? 'is-dragging' : undefined}>
                        {/* For the mouse and touch; keyboard users have the arrows. */}
                        <span
                          className="music-drag-handle"
                          title="Drag to move"
                          aria-hidden="true"
                          onPointerDown={(event) => startDrag(event, id)}
                        >
                          ⠿
                        </span>
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
                          aria-disabled={index === editIds.length - 1}
                          onClick={() => moveSong(index, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          className="secondary-button small-button"
                          aria-label={`Remove ${title} from the playlist`}
                          title="Remove from the playlist"
                          onClick={() => removeSong(index)}
                        >
                          Remove
                        </button>
                      </li>
                    )
                  })}
                </ol>
                {songs.some((song) => song.kind !== 'spotify' && !editIds.includes(song.id)) ? (
                  <div className="music-add-songs">
                    <label htmlFor="music-add-songs-list">Add songs</label>
                    <p className="music-playlist-hint" id="music-add-songs-hint">
                      Choose one or more (hold Cmd on a Mac, or Ctrl, to choose several), then press Add.
                    </p>
                    <select
                      id="music-add-songs-list"
                      multiple
                      size={8}
                      aria-describedby="music-add-songs-hint"
                      value={songsToAdd}
                      onChange={(event) => setSongsToAdd([...event.target.selectedOptions].map((option) => option.value))}
                    >
                      {songs
                        .filter((song) => song.kind !== 'spotify' && !editIds.includes(song.id))
                        .map((song) => (
                          <option key={song.id} value={song.id}>
                            {song.title}
                          </option>
                        ))}
                    </select>
                    <button type="button" className="secondary-button" disabled={songsToAdd.length === 0} onClick={addChosenSongs}>
                      {songsToAdd.length > 1 ? `Add the ${songsToAdd.length} songs` : 'Add'}
                    </button>
                  </div>
                ) : (
                  <p className="music-playlist-hint">Every song on the site is in this playlist.</p>
                )}
                <div className="music-reorder-actions">
                  <button type="button" className="primary-button" disabled={isBusy || editIds.length === 0} onClick={handleSaveEdit}>
                    Save changes
                  </button>
                  <button type="button" className="secondary-button" disabled={isBusy} onClick={() => setEditIds(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {chosenPlaylist && !editIds && (
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
                  {/* Sharing is for accounts an administrator allowed; a shared playlist can always be unshared. */}
                  {(user?.share_lists || chosenPlaylist.shared) && (
                    <button type="button" className="link-button" disabled={isBusy} onClick={handleShare}>
                      {chosenPlaylist.shared ? 'Stop sharing' : 'Share on Public lists'}
                    </button>
                  )}
                  {chosenPlaylist.shared && (
                    <button type="button" className="link-button" onClick={handleCopyLink}>
                      Copy link
                    </button>
                  )}
                  <button type="button" className="link-button" onClick={handleExport}>
                    Export this playlist
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
      {!user && playing && playingSong && (
        <p className="music-now-playing" role="status">
          Playing “{playing.name}”: song {playing.index + 1} of {playing.songIds.length}, <strong>{playingSong.title}</strong>{' '}
          <button type="button" className="secondary-button small-button" onClick={handleStop}>
            Stop
          </button>
        </p>
      )}
      {!user && message && <p role="status">{message}</p>}
      {user && (
        <PlaylistSaveBox
          tickedIds={tickedSongs.map((song) => song.id)}
          playlists={playlists}
          name={playlistName}
          onNameChange={setPlaylistName}
          onSaved={(playlist) => {
            keepPlaylist(playlist)
            setEditIds(null)
            setMessage('')
            setTickedIds(new Set())
          }}
          onClear={() => setTickedIds(new Set())}
          afterSaving="Open Your playlists above to play it."
        />
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
                  // Spotify's player cannot be paused from here: loading it again stops it.
                  event.currentTarget.querySelectorAll<HTMLIFrameElement>('iframe.music-spotify').forEach((player) => {
                    const address = player.src
                    player.src = 'about:blank'
                    player.src = address
                  })
                }
              }}
            >
              <summary>
                <span className="music-title">{song.title}</span>
                {song.author && <span className="music-author">{song.author}</span>}
              </summary>
              <div className="music-body">
                {song.kind === 'spotify' && song.spotify_embed ? (
                  // Spotify's own player (2026-11-19): full tracks for a visitor signed in to Spotify in this browser,
                  // 30-second previews otherwise. It loads only once the section is opened (lazy, inside closed details).
                  <iframe
                    className="music-spotify"
                    src={song.spotify_embed}
                    title={`${song.title} on Spotify`}
                    height={song.spotify_link?.startsWith('track/') || song.spotify_link?.startsWith('episode/') ? 152 : 380}
                    loading="lazy"
                    allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                  />
                ) : song.kind === 'video' ? (
                  // No Download in the player's menu, and no "Save video as" on right-click (the owner's request,
                  // 2026-11-22). This hides the easy ways; it cannot stop a determined visitor saving the file.
                  <video
                    className="music-video"
                    controls
                    controlsList="nodownload"
                    onContextMenu={(event) => event.preventDefault()}
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
                    controlsList="nodownload"
                    onContextMenu={(event) => event.preventDefault()}
                    preload="none"
                    src={musicFileAddress(song)}
                    onPlay={(event) => handlePlay(event.currentTarget, song.id)}
                    onEnded={() => handleEnded(song.id)}
                  >
                    Your browser cannot play this recording.
                  </audio>
                )}
                {/* The words first (formatted from a document, or as typed), then the words file below them when
                    there is one (it loads only once the song is opened): the owner's request, 2026-11-21. */}
                {song.lyrics_html && (
                  // The words from a PDF or Word document, with their formatting (cleaned by the server).
                  <div className="music-lyrics formatted-text" dangerouslySetInnerHTML={{ __html: formattedHtmlForPage(song.lyrics_html) }} />
                )}
                {!song.lyrics_html && song.lyrics && (
                  <div className="music-lyrics">
                    {song.lyrics.split(/\n{2,}/).map((verse, index) => (
                      <p key={index}>{verse}</p>
                    ))}
                  </div>
                )}
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
              </div>
            </details>
            {user && song.kind === 'spotify' && (
              // A Spotify item cannot go in a playlist (the site cannot tell when Spotify's player ends a track); an
              // empty space keeps the column of ticks lined up.
              <span className="music-tick music-tick-none" aria-hidden="true" />
            )}
            {user && song.kind !== 'spotify' && (
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
