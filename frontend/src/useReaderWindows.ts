import { useEffect, useRef } from 'react'
import type { ContextKind, VerseTarget } from './types'
import { useVerseWindows } from './useVerseWindows'

// The verse windows of a long, scrolling page (a Bible or a commentary being read). A window hides
// the reading, so the page's place is kept when one opens and put back when the last one closes.
//
// session is any object that changes when the reader goes somewhere else; that closes the windows.
export function useReaderWindows(session: object) {
  const windows = useVerseWindows(session, true)
  const isOpen = windows.isShowing
  const savedScroll = useRef(0)
  const wasOpen = useRef(false)

  useEffect(() => {
    if (wasOpen.current && !isOpen) {
      window.scrollTo(0, savedScroll.current)
    }
    wasOpen.current = isOpen
  }, [isOpen])

  // Open a window over the reading, from the link that was used.
  function open(
    kind: ContextKind,
    target: VerseTarget,
    trigger: HTMLElement,
    options: { commentaryId?: string | null } = {},
  ) {
    savedScroll.current = window.scrollY
    windows.open(session, kind, target, trigger, options)
    window.scrollTo(0, 0)
  }

  return { ...windows, isOpen, open }
}
