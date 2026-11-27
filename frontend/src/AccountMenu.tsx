import { useEffect, useRef, useState } from 'react'
import type { FocusEvent, PointerEvent } from 'react'
import { headShotAddress } from './api'
import type { AccountUser } from './types'

interface AccountMenuProps {
  // Who is logged in (nobody, unless they chose to).
  user: AccountUser | null
  // False while "Login required" is on: only an administrator sets up accounts then (Site users).
  canSetUpAccount: boolean
  onShowAccount: () => void
  onShowNotes: () => void
  onShowLists: () => void
  onShowCards: () => void
  onShowTasks: () => void
  onLogIn: () => void
  onSetUpAccount: () => void
  onLogOut: () => void
}

// How long the menu stays open after the mouse leaves it, so moving from the icon to an entry does not close it.
const CLOSE_DELAY_MILLISECONDS = 300

// The outline of a head and shoulders in a circle: the account icon when the member has no picture (or nobody is
// logged in).
export function PersonOutline() {
  return (
    <svg className="account-person" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <circle cx="20" cy="20" r="18.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="20" cy="15" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M8.5 32.5c1.8-6 6.3-9 11.5-9s9.7 3 11.5 9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

// The name a menu shows for the member: their name, else their address or phone.
function displayName(user: AccountUser): string {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ')
  return name || user.email || user.phone
}

// The account icon at the far top right (added 2026-11-23 at the owner's request, in place of the row of links): the
// member's head shot, or the outline of a head and shoulders. Hovering over it with a mouse, or clicking it, opens a
// menu: Account settings, My notes, My lists, My cards, My scheduled tasks (only for a member who has some) and Log out, or Log in and Set up account for a visitor. Escape, a click
// elsewhere or choosing an entry closes it.
function AccountMenu({ user, canSetUpAccount, onShowAccount, onShowNotes, onShowLists, onShowCards, onShowTasks, onLogIn, onSetUpAccount, onLogOut }: AccountMenuProps) {
  const [isOpen, setIsOpen] = useState(false)
  // The picture address that would not load (then the outline shows instead).
  const [failedPicture, setFailedPicture] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const closeTimer = useRef<number | undefined>(undefined)
  const picture = user?.head_shot && user.head_shot !== failedPicture ? headShotAddress(user.head_shot) : null

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [isOpen])

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  // Hovering opens it only for a mouse: on a phone the tap is the click, which toggles it.
  const openOnHover = (event: PointerEvent) => {
    if (event.pointerType !== 'mouse') {
      return
    }
    window.clearTimeout(closeTimer.current)
    setIsOpen(true)
  }
  const closeAfterHover = (event: PointerEvent) => {
    if (event.pointerType !== 'mouse') {
      return
    }
    window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => {
      // Not while the keyboard is in the menu.
      if (!wrapperRef.current?.contains(document.activeElement) || document.activeElement === buttonRef.current) {
        setIsOpen(false)
      }
    }, CLOSE_DELAY_MILLISECONDS)
  }
  // Tabbing out of the menu closes it. (A blur with nowhere new to go is a click, which Safari does not focus;
  // a click outside is handled above.)
  const closeWhenFocusLeaves = (event: FocusEvent) => {
    const next = event.relatedTarget as Node | null
    if (next && !wrapperRef.current?.contains(next)) {
      setIsOpen(false)
    }
  }
  const choose = (action: () => void) => () => {
    window.clearTimeout(closeTimer.current)
    setIsOpen(false)
    action()
  }

  const label = user ? `Account menu for ${displayName(user)}` : 'Account menu: log in or set up an account'
  return (
    <div
      ref={wrapperRef}
      className={`account-menu${isOpen ? ' is-open' : ''}`}
      onPointerEnter={openOnHover}
      onPointerLeave={closeAfterHover}
      onBlur={closeWhenFocusLeaves}
    >
      <button
        ref={buttonRef}
        type="button"
        className={`account-menu-button${picture ? ' has-picture' : ''}`}
        aria-label={label}
        aria-expanded={isOpen}
        aria-controls="account-menu-list"
        onClick={() => setIsOpen(!isOpen)}
      >
        {picture ? <img src={picture} alt="" onError={() => setFailedPicture(user?.head_shot ?? null)} /> : <PersonOutline />}
      </button>
      {isOpen && (
        <div id="account-menu-list" className="account-menu-list">
          {user && (
            <div className="account-menu-who">
              <strong>{displayName(user)}</strong>
              {(user.email || user.phone) && displayName(user) !== (user.email || user.phone) && (
                <span>{user.email || user.phone}</span>
              )}
            </div>
          )}
          <ul>
            {user ? (
              <>
                <li>
                  <button type="button" onClick={choose(onShowAccount)}>Account settings</button>
                </li>
                <li>
                  <button type="button" onClick={choose(onShowNotes)}>My notes</button>
                </li>
                <li>
                  <button type="button" onClick={choose(onShowLists)}>My lists</button>
                </li>
                <li>
                  <button type="button" onClick={choose(onShowCards)}>My cards</button>
                </li>
                {user.has_scheduled_tasks && (
                  <li>
                    <button type="button" onClick={choose(onShowTasks)}>My scheduled tasks</button>
                  </li>
                )}
                <li className="account-menu-separated">
                  <button type="button" onClick={choose(onLogOut)}>Log out</button>
                </li>
              </>
            ) : (
              <>
                <li>
                  <button type="button" onClick={choose(onLogIn)}>Log in</button>
                </li>
                {canSetUpAccount && (
                  <li>
                    <button type="button" onClick={choose(onSetUpAccount)}>Set up account</button>
                  </li>
                )}
              </>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

export default AccountMenu
