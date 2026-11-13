import { useState } from 'react'
import { savePlaylist } from './api'
import type { Playlist } from './api'

interface PlaylistSaveBoxProps {
  // The ticked songs, in the order a new playlist plays them.
  tickedIds: string[]
  // The visitor's playlists, to tell a new name from one already used (saving under it replaces that playlist).
  playlists: Playlist[]
  name: string
  onNameChange: (name: string) => void
  // After a save: the playlist as saved. The page clears its ticks and keeps the playlist in its list.
  onSaved: (playlist: Playlist) => void
  onClear: () => void
  // Where the visitor finds the playlist afterwards, said after "Saved the playlist ...".
  afterSaving: string
}

// The box that saves ticked songs as a playlist: a name and Save (Replace when the name is already used), and
// Clear the ticks. Used on the music page and the music search. Replacing a playlist keeps the order of the
// songs it already had; songs newly ticked go at the end, in the order given.
function PlaylistSaveBox({ tickedIds, playlists, name, onNameChange, onSaved, onClear, afterSaving }: PlaylistSaveBoxProps) {
  const [isBusy, setIsBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const trimmedName = name.trim().replace(/\s+/g, ' ')
  const existing = playlists.find((playlist) => playlist.name.toLowerCase() === trimmedName.toLowerCase())

  async function handleSave() {
    setIsBusy(true)
    setMessage('')
    setErrorMessage('')
    const ticked = new Set(tickedIds)
    const kept = existing ? existing.song_ids.filter((id) => ticked.has(id)) : []
    const added = tickedIds.filter((id) => !kept.includes(id))
    try {
      const { playlist, replaced } = await savePlaylist(trimmedName, [...kept, ...added])
      onSaved(playlist)
      onNameChange('')
      const count = playlist.song_ids.length
      setMessage(`${replaced ? 'Replaced' : 'Saved'} the playlist “${playlist.name}” (${count} ${count === 1 ? 'song' : 'songs'}). ${afterSaving}`)
    } catch (error) {
      setErrorMessage((error as Error).message)
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <>
      {tickedIds.length > 0 && (
        <section className="music-playlist-save" aria-label="Save the ticked songs as a playlist">
          <p>
            {tickedIds.length} {tickedIds.length === 1 ? 'song' : 'songs'} ticked.
          </p>
          <label>
            Playlist name
            <input
              type="text"
              value={name}
              maxLength={100}
              onChange={(event) => onNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  // The music search is a form; Enter here saves the playlist, not the search.
                  event.preventDefault()
                  if (trimmedName && !isBusy) {
                    handleSave()
                  }
                }
              }}
            />
          </label>
          <button type="button" className="primary-button" disabled={isBusy || !trimmedName} onClick={handleSave}>
            {existing ? 'Replace the playlist' : 'Save as a playlist'}
          </button>
          <button type="button" className="secondary-button" onClick={onClear}>
            Clear the ticks
          </button>
          {existing && (
            <p className="music-playlist-hint">
              You already have a playlist called “{trimmedName}”; saving replaces its songs (keeping their order).
            </p>
          )}
        </section>
      )}
      {(message || errorMessage) && (
        <div className="music-save-messages">
          {message && <p role="status">{message}</p>}
          {errorMessage && (
            <p className="error" role="alert">
              {errorMessage}
            </p>
          )}
        </div>
      )}
    </>
  )
}

export default PlaylistSaveBox
