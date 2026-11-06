import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

// A neighbour of a chapter: where to read on to (or back to), across book boundaries.
export interface StripNeighbour {
  book_number: number
  chapter: number
}

export interface StripChapter {
  book_number: number
  chapter: number
  previous: StripNeighbour | null
  next: StripNeighbour | null
}

// Far-off chapters are dropped so a long read does not pile up thousands of elements.
const maximumLoadedChapters = 9
// Start loading the next chapter this long before it would scroll into view.
const loadAheadMargin = '1200px 0px'
// After a jump to the top, chapters are not added above until the reader has scrolled this far down.
const releaseTopDistance = 800

export function chapterKey(book: number, chapter: number) {
  return `${book}:${chapter}`
}

// Continuous reading: chapters one after another that grow as the reader scrolls, up or down.
//
// start() loads the chapter to read first. After that the chapters before and after it are loaded
// when their ends come near, so the reader can scroll on past the starting point in either
// direction. Loading chapters above the screen must not move what is being read, so the chapter at
// the top of the screen is remembered before the change and put back at the same place after it.
//
// load fetches one chapter. Put the element returned by topSentinel and bottomSentinel at the
// ends of the list, and give each chapter's element the ref from registerChapter(book, chapter).
export function useChapterStrip<Chapter extends StripChapter>(
  load: (book: number, chapter: number, signal: AbortSignal) => Promise<Chapter>,
) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [isStarting, setIsStarting] = useState(false)
  const [extending, setExtending] = useState<'previous' | 'next' | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  // The chapter at the top of the screen, as the reader scrolls.
  const [visibleChapter, setVisibleChapter] = useState<{ book: number; chapter: number } | null>(null)
  const [topElement, setTopElement] = useState<HTMLElement | null>(null)
  const [bottomElement, setBottomElement] = useState<HTMLElement | null>(null)

  const loadRef = useRef(load)
  const chaptersRef = useRef<Chapter[]>([])
  const controller = useRef<AbortController | null>(null)
  const isBusy = useRef(false)
  const elements = useRef(new Map<string, HTMLElement>())
  const anchor = useRef<{ key: string; top: number } | null>(null)
  const extendRef = useRef<(direction: 'previous' | 'next') => void>(() => {})
  // Set by a jump to the top. Adding chapters above would carry the reader away from the top again.
  const isHoldingTop = useRef(false)

  useEffect(() => {
    loadRef.current = load
    chaptersRef.current = chapters
  })

  // The first chapter on screen, and where its top edge is, so it can be put back after a change.
  function captureAnchor() {
    for (const chapter of chaptersRef.current) {
      const key = chapterKey(chapter.book_number, chapter.chapter)
      const rectangle = elements.current.get(key)?.getBoundingClientRect()
      if (rectangle && rectangle.bottom > 0) {
        anchor.current = { key, top: rectangle.top }
        return
      }
    }
  }

  useLayoutEffect(() => {
    if (anchor.current === null) {
      return
    }
    const rectangle = elements.current.get(anchor.current.key)?.getBoundingClientRect()
    if (rectangle) {
      window.scrollBy(0, rectangle.top - anchor.current.top)
    }
    anchor.current = null
  }, [chapters])

  // Load the chapter to start reading at, replacing what is shown. Resolves true once it is shown.
  const start = useCallback(async (book: number, chapter: number) => {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    isBusy.current = false
    setIsStarting(true)
    setErrorMessage('')
    try {
      const first = await loadRef.current(book, chapter, request.signal)
      if (request.signal.aborted) {
        return false
      }
      anchor.current = null
      setChapters([first])
      setVisibleChapter({ book, chapter })
      setIsStarting(false)
      return true
    } catch (error) {
      if (!request.signal.aborted) {
        setErrorMessage(error instanceof Error ? error.message : 'Could not load the chapter.')
        setIsStarting(false)
      }
      return false
    }
  }, [])

  async function extend(direction: 'previous' | 'next') {
    const list = chaptersRef.current
    const request = controller.current
    if (isBusy.current || list.length === 0 || request === null) {
      return
    }
    const edgeChapter = direction === 'previous' ? list[0] : list[list.length - 1]
    const neighbour = direction === 'previous' ? edgeChapter.previous : edgeChapter.next
    if (neighbour === null || (direction === 'previous' && isHoldingTop.current)) {
      return
    }
    isBusy.current = true
    setExtending(direction)
    try {
      const loaded = await loadRef.current(neighbour.book_number, neighbour.chapter, request.signal)
      const latest = chaptersRef.current
      const latestEdge = direction === 'previous' ? latest[0] : latest[latest.length - 1]
      // Something else was started or loaded while this was on its way.
      if (request.signal.aborted || latestEdge !== edgeChapter || (direction === 'previous' && isHoldingTop.current)) {
        return
      }
      captureAnchor()
      setChapters((shown) =>
        direction === 'previous'
          ? [loaded, ...shown].slice(0, maximumLoadedChapters)
          : [...shown, loaded].slice(-maximumLoadedChapters),
      )
    } catch (error) {
      if (!request.signal.aborted) {
        setErrorMessage(error instanceof Error ? error.message : 'Could not load the chapter.')
      }
    } finally {
      isBusy.current = false
      setExtending(null)
    }
  }

  useEffect(() => {
    extendRef.current = extend
  })

  // Watch the two ends of the list. The watch is set up again after every change, so an end that is
  // still near after a chapter was added loads the next one.
  useEffect(() => {
    if (topElement === null && bottomElement === null) {
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            extendRef.current(entry.target === topElement ? 'previous' : 'next')
          }
        }
      },
      { rootMargin: loadAheadMargin },
    )
    if (topElement) {
      observer.observe(topElement)
    }
    if (bottomElement) {
      observer.observe(bottomElement)
    }
    return () => observer.disconnect()
  }, [topElement, bottomElement, chapters])

  // Which chapter is at the top of the screen, for the book and chapter choosers to follow.
  useEffect(() => {
    let frame = 0
    function update() {
      frame = 0
      for (const chapter of chaptersRef.current) {
        const rectangle = elements.current.get(chapterKey(chapter.book_number, chapter.chapter))?.getBoundingClientRect()
        if (rectangle && rectangle.bottom > 140) {
          setVisibleChapter((shown) =>
            shown?.book === chapter.book_number && shown.chapter === chapter.chapter
              ? shown
              : { book: chapter.book_number, chapter: chapter.chapter },
          )
          return
        }
      }
    }
    function handleScroll() {
      if (window.scrollY > releaseTopDistance) {
        isHoldingTop.current = false
      }
      if (frame === 0) {
        frame = window.requestAnimationFrame(update)
      }
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', handleScroll)
      window.cancelAnimationFrame(frame)
    }
  }, [])

  // Go to the very top of the page. Until the reader scrolls down again no chapters are added above,
  // because adding them would move the page and the top would slip away.
  const scrollToTop = useCallback(() => {
    isHoldingTop.current = true
    window.scrollTo(0, 0)
  }, [])

  const registerChapter = useCallback(
    (book: number, chapter: number) => (element: HTMLElement | null) => {
      const key = chapterKey(book, chapter)
      if (element) {
        elements.current.set(key, element)
      } else {
        elements.current.delete(key)
      }
    },
    [],
  )

  return {
    chapters,
    isStarting,
    extending,
    errorMessage,
    visibleChapter,
    start,
    scrollToTop,
    registerChapter,
    topSentinel: setTopElement,
    bottomSentinel: setBottomElement,
  }
}
