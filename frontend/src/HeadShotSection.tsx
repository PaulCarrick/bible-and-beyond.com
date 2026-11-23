import { useRef, useState } from 'react'
import { headShotAddress, removeHeadShot, saveHeadShot } from './api'
import { PersonOutline } from './AccountMenu'
import type { AccountUser } from './types'

interface HeadShotSectionProps {
  user: AccountUser
  onUserChanged: (user: AccountUser) => void
}

// The side of the square the page sends; the server makes it 400 (head_shots.SIZE).
const SENT_SIZE = 600

// The middle square of the chosen photo, SENT_SIZE wide, as a JPEG: a phone's photo of several MB becomes about
// 100 KB, under the API's 1 MB limit, turned the way the camera meant. The server reads it again and keeps no EXIF.
async function headShotPicture(file: File): Promise<Blob> {
  let source: CanvasImageSource
  let width: number
  let height: number
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    source = bitmap
    width = bitmap.width
    height = bitmap.height
  } catch {
    // A browser without createImageBitmap's options, or a picture it cannot read that way.
    const image = new Image()
    const address = URL.createObjectURL(file)
    try {
      image.src = address
      await image.decode()
    } catch {
      throw new Error('That file is not a picture this browser can read. Please choose a JPEG, PNG or WebP photo.')
    } finally {
      URL.revokeObjectURL(address)
    }
    source = image
    width = image.naturalWidth
    height = image.naturalHeight
  }
  const side = Math.min(width, height)
  const canvas = document.createElement('canvas')
  canvas.width = SENT_SIZE
  canvas.height = SENT_SIZE
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('This browser cannot prepare the picture.')
  }
  context.fillStyle = '#fff'
  context.fillRect(0, 0, SENT_SIZE, SENT_SIZE)
  context.drawImage(source, (width - side) / 2, (height - side) / 2, side, side, 0, 0, SENT_SIZE, SENT_SIZE)
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The picture could not be prepared.'))), 'image/jpeg', 0.88)
  })
}

// "Your picture" on the My account page (added 2026-11-23 at the owner's request): a head shot shown in the account
// icon at the top right. Only the member sees it. Choosing a photo saves it at once (its middle square); Remove
// takes it away. A plain container, not a form (see "Notes" in CLAUDE.md).
function HeadShotSection({ user, onUserChanged }: HeadShotSectionProps) {
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  async function choose(file: File | undefined) {
    if (!file || isSaving) {
      return
    }
    setMessage('')
    setErrorMessage('')
    setIsSaving(true)
    try {
      onUserChanged(await saveHeadShot(await headShotPicture(file)))
      setMessage('Your picture has been saved.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The picture could not be saved.')
    } finally {
      setIsSaving(false)
      if (inputRef.current) {
        inputRef.current.value = ''
      }
    }
  }

  async function remove() {
    setMessage('')
    setErrorMessage('')
    setIsSaving(true)
    try {
      onUserChanged(await removeHeadShot())
      setMessage('Your picture has been removed.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The picture could not be removed.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="head-shot-section" aria-labelledby="head-shot-heading">
      <h2 id="head-shot-heading">Your picture</h2>
      <div className="head-shot-row">
        <div className="head-shot-preview">
          {user.head_shot ? <img src={headShotAddress(user.head_shot)} alt="Your picture" /> : <PersonOutline />}
        </div>
        <div className="head-shot-actions">
          <p className="account-note">
            A head shot for the account icon at the top right of the site. Only you see it. The middle of the photo
            is kept, as a square.
          </p>
          <div className="note-actions">
            <input
              ref={inputRef}
              id="head-shot-file"
              className="visually-hidden"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              disabled={isSaving}
              onChange={(event) => void choose(event.target.files?.[0])}
            />
            <button type="button" className="primary-button" disabled={isSaving} onClick={() => inputRef.current?.click()}>
              {isSaving ? 'Saving…' : user.head_shot ? 'Choose another picture…' : 'Choose a picture…'}
            </button>
            {user.head_shot && (
              <button type="button" className="secondary-button" disabled={isSaving} onClick={() => void remove()}>
                Remove the picture
              </button>
            )}
          </div>
          {message && <p role="status">{message}</p>}
          {errorMessage && <p className="error" role="alert">{errorMessage}</p>}
        </div>
      </div>
    </section>
  )
}

export default HeadShotSection
