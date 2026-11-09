import { useEffect, useLayoutEffect, useRef, useState } from 'react'

// How long the pointer rests on something before its tooltip shows, in milliseconds.
const SHOW_DELAY = 400
// The space kept between the tooltip and the element, and between the tooltip and the window's edges.
const GAP = 8

interface ShownTooltip {
  text: string
  // The element's box when the tooltip was asked for.
  anchor: DOMRect
}

// The tooltip text of an element: its title, or the copy kept in data-tooltip once the title was moved there.
function tooltipTextOf(element: HTMLElement): string {
  return element.getAttribute('title') || element.dataset.tooltip || ''
}

// Moves an element's title to data-tooltip, so the browser's own small tooltip does not show as well as this
// one. A screen reader still hears it: it becomes the aria-description unless the element has one.
function takeTitle(element: HTMLElement) {
  const title = element.getAttribute('title')
  if (!title) {
    return
  }
  element.dataset.tooltip = title
  element.removeAttribute('title')
  if (!element.hasAttribute('aria-description') && element.getAttribute('aria-label') !== title) {
    element.setAttribute('aria-description', title)
  }
}

function findTooltipElement(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) {
    return null
  }
  return target.closest<HTMLElement>('[title], [data-tooltip]')
}

// One tooltip for the whole site, larger and easier to read than the browser's. Every element with a title
// gets it, so the components keep using the plain title attribute. It shows after a short rest of the mouse
// pointer, or at once when the keyboard moves focus to the element, and hides when the pointer leaves, on a
// click, a scroll or Escape. Not on touch screens, where a tap is a click.
function SiteTooltip() {
  const [shown, setShown] = useState<ShownTooltip | null>(null)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)
  const boxReference = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let timer: number | undefined
    let current: HTMLElement | null = null

    function hide() {
      window.clearTimeout(timer)
      current = null
      setShown(null)
    }

    function show(element: HTMLElement) {
      const text = tooltipTextOf(element)
      if (text) {
        setShown({ text, anchor: element.getBoundingClientRect() })
      }
    }

    function handlePointerOver(event: PointerEvent) {
      if (event.pointerType === 'touch') {
        return
      }
      const element = findTooltipElement(event.target)
      if (element === current) {
        return
      }
      hide()
      if (!element) {
        return
      }
      takeTitle(element)
      current = element
      timer = window.setTimeout(() => show(element), SHOW_DELAY)
    }

    function handlePointerOut(event: PointerEvent) {
      if (current && !current.contains(event.relatedTarget as Node | null)) {
        hide()
      }
    }

    function handleFocusIn(event: FocusEvent) {
      const element = findTooltipElement(event.target)
      if (!element || !(event.target as Element).matches(':focus-visible')) {
        return
      }
      hide()
      takeTitle(element)
      current = element
      show(element)
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        hide()
      }
    }

    document.addEventListener('pointerover', handlePointerOver)
    document.addEventListener('pointerout', handlePointerOut)
    document.addEventListener('pointerdown', hide)
    document.addEventListener('focusin', handleFocusIn)
    document.addEventListener('focusout', hide)
    document.addEventListener('keydown', handleKeyDown)
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('pointerover', handlePointerOver)
      document.removeEventListener('pointerout', handlePointerOut)
      document.removeEventListener('pointerdown', hide)
      document.removeEventListener('focusin', handleFocusIn)
      document.removeEventListener('focusout', hide)
      document.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [])

  // Below the element, centred on it and kept inside the window; above it when there is no room below.
  useLayoutEffect(() => {
    const box = boxReference.current
    if (!shown || !box) {
      setPosition(null)
      return
    }
    const { anchor } = shown
    const width = box.offsetWidth
    const height = box.offsetHeight
    const left = Math.min(Math.max(GAP, anchor.left + anchor.width / 2 - width / 2), window.innerWidth - width - GAP)
    const below = anchor.bottom + GAP
    const top = below + height + GAP <= window.innerHeight ? below : Math.max(GAP, anchor.top - height - GAP)
    setPosition({ left, top })
  }, [shown])

  if (!shown) {
    return null
  }
  return (
    <div
      ref={boxReference}
      className="site-tooltip"
      aria-hidden="true"
      style={position ? { left: position.left, top: position.top } : { left: 0, top: 0, visibility: 'hidden' }}
    >
      {shown.text}
    </div>
  )
}

export default SiteTooltip
