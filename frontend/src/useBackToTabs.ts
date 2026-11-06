import { useEffect, useState } from 'react'

// The ways back to the tabs at the top of the page from a long read. Chapters keep loading above the
// reader, so the browser's own jump to the top never arrives; scrollToTop (from useChapterStrip)
// does the jump and holds the page there.

// The Home key (also Ctrl+Home and Cmd+Up Arrow) goes to the top, except while typing in a field.
// Returns whether the reader has scrolled far enough down for the "Back to tabs" button to show.
export function useBackToTabs(isHidden: boolean, isWindowOpen: boolean, scrollToTop: () => void) {
  const [isScrolledDown, setIsScrolledDown] = useState(false)

  useEffect(() => {
    if (isHidden || isWindowOpen) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      const isHome = event.key === 'Home' && !event.shiftKey && !event.altKey && !event.metaKey
      const isCommandUp = event.key === 'ArrowUp' && event.metaKey && !event.shiftKey && !event.altKey && !event.ctrlKey
      const target = event.target as HTMLElement | null
      const isTyping =
        target !== null && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
      if ((isHome || isCommandUp) && !isTyping) {
        event.preventDefault()
        scrollToTop()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isHidden, isWindowOpen, scrollToTop])

  useEffect(() => {
    if (isHidden) {
      return
    }
    function handleScroll() {
      setIsScrolledDown(window.scrollY > 500)
    }
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [isHidden])

  return isScrolledDown
}
