import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { ContextKind } from './types'

export interface VerseMenuItem {
  kind: ContextKind
  label: string
}

interface VerseMenuProps {
  // Where the menu opens: the pointer, or the corner of the verse number for a keyboard or a tap.
  x: number
  y: number
  // The verse the menu is about, such as "John 3:16".
  heading: string
  items: VerseMenuItem[]
  onChoose: (kind: ContextKind) => void
  onClose: () => void
}

const edgeMargin = 8

// A small menu of what can be done with a verse. It opens at the pointer and stays inside the window.
// Arrow keys move through it, Enter chooses, Escape or a click elsewhere closes it.
function VerseMenu({ x, y, heading, items, onChoose, onClose }: VerseMenuProps) {
  const menu = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: x, top: y })

  useLayoutEffect(() => {
    const box = menu.current?.getBoundingClientRect()
    if (box) {
      setPosition({
        left: Math.max(edgeMargin, Math.min(x, window.innerWidth - box.width - edgeMargin)),
        top: Math.max(edgeMargin, Math.min(y, window.innerHeight - box.height - edgeMargin)),
      })
    }
  }, [x, y])

  useEffect(() => {
    menu.current?.querySelector<HTMLButtonElement>('button')?.focus()
    function closeOnOutsideClick(event: MouseEvent) {
      if (menu.current && !menu.current.contains(event.target as Node)) {
        onClose()
      }
    }
    // Scrolling or resizing would leave the menu away from its verse.
    window.addEventListener('mousedown', closeOnOutsideClick)
    window.addEventListener('scroll', onClose, { passive: true })
    window.addEventListener('resize', onClose)
    return () => {
      window.removeEventListener('mousedown', closeOnOutsideClick)
      window.removeEventListener('scroll', onClose)
      window.removeEventListener('resize', onClose)
    }
  }, [onClose])

  function handleKeyDown(event: ReactKeyboardEvent) {
    const buttons = [...(menu.current?.querySelectorAll<HTMLButtonElement>('button') ?? [])]
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      buttons[(index + 1) % buttons.length]?.focus()
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      buttons[(index - 1 + buttons.length) % buttons.length]?.focus()
    } else if (event.key === 'Home') {
      event.preventDefault()
      buttons[0]?.focus()
    } else if (event.key === 'End') {
      event.preventDefault()
      buttons[buttons.length - 1]?.focus()
    } else if (event.key === 'Tab') {
      event.preventDefault()
      onClose()
    }
  }

  return (
    <div
      ref={menu}
      className="verse-menu"
      role="menu"
      aria-label={`Options for ${heading}`}
      style={{ left: position.left, top: position.top }}
      onKeyDown={handleKeyDown}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="verse-menu-heading">{heading}</div>
      {items.map((item) => (
        <button type="button" role="menuitem" key={item.kind} className="verse-menu-item" onClick={() => onChoose(item.kind)}>
          {item.label}
        </button>
      ))}
    </div>
  )
}

export default VerseMenu
