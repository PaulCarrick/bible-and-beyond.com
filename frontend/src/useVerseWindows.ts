import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchCommentaries,
  fetchContext,
  fetchLexiconEntry,
  fetchOriginalWords,
  fetchParallel,
  fetchRelated,
} from './api'
import type { WindowView } from './ContextWindow'
import type { ContextKind, RelatedDirection, VerseTarget } from './types'

interface WindowState<Key> {
  // What was on screen when the window was opened (a page of search results, a chapter being read).
  // Showing something else closes the window.
  openedFor: Key
  // The windows opened one from another; the last one is showing and Back removes it.
  views: WindowView[]
}

interface OpenOptions {
  direction?: RelatedDirection
  commentaryId?: string | null
}

// The windows that open over a page: the verse in context, its chapter, other translations,
// related verses, Hebrew and Greek words, lexicon entries and commentaries. A window can open
// another on top of itself; Back removes the top one, and Close (or Escape) removes them all.
//
// currentKey is whatever the page is showing now: windows opened for something else stay hidden.
// isReady is false while the page is loading, which also hides them.
export function useVerseWindows<Key>(currentKey: Key | null, isReady: boolean) {
  const [windowState, setWindowState] = useState<WindowState<Key> | null>(null)
  const request = useRef<AbortController | null>(null)
  const trigger = useRef<HTMLElement | null>(null)
  const nextViewId = useRef(1)

  const isShowing = windowState !== null && windowState.openedFor === currentKey && isReady
  const views = windowState ? windowState.views : []
  const currentView = views.length > 0 ? views[views.length - 1] : null

  function updateView(id: number, changes: Partial<WindowView>) {
    setWindowState((current) =>
      current
        ? { ...current, views: current.views.map((view) => (view.id === id ? { ...view, ...changes } : view)) }
        : current,
    )
  }

  // Ask the server for what a window shows, and put the answer in that window.
  function loadView(view: WindowView) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller

    const { translation, book_number: book, chapter, verse } = view.target
    const answer =
      view.kind === 'parallel'
        ? fetchParallel(book, chapter, verse, controller.signal).then((parallel) => ({ parallel }))
        : view.kind === 'related'
          ? fetchRelated(translation, book, chapter, verse, view.direction, controller.signal).then(
              (related) => ({ related }),
            )
          : view.kind === 'words'
            ? fetchOriginalWords(book, chapter, verse, controller.signal).then((words) => ({ words }))
            : view.kind === 'lexicon'
              ? fetchLexiconEntry(translation, view.target.strong_code ?? '', controller.signal).then(
                  (lexicon) => ({ lexicon }),
                )
              : view.kind === 'commentary'
                ? fetchCommentaries(book, chapter, verse, view.commentaryId, controller.signal).then(
                    (commentary) => ({ commentary }),
                  )
                : fetchContext(view.kind, translation, book, chapter, verse, controller.signal).then(
                    (context) => ({ context }),
                  )
    answer
      .then((loaded) => updateView(view.id, { ...loaded, errorMessage: '' }))
      .catch((error) => {
        if (controller.signal.aborted) {
          return
        }
        updateView(view.id, {
          errorMessage: error instanceof Error ? error.message : 'Could not load the verses.',
        })
      })
  }

  function newView(kind: ContextKind, target: VerseTarget, options: OpenOptions = {}): WindowView {
    const id = nextViewId.current
    nextViewId.current += 1
    return {
      id,
      kind,
      target,
      direction: options.direction ?? 'from',
      context: null,
      parallel: null,
      related: null,
      words: null,
      lexicon: null,
      commentary: null,
      commentaryId: options.commentaryId ?? null,
      errorMessage: '',
    }
  }

  // A link on the page: open a window in place of what the page shows. The element that was used
  // gets the keyboard focus back when the window closes.
  function open(
    key: Key,
    kind: ContextKind,
    target: VerseTarget,
    triggerElement: HTMLElement,
    options: OpenOptions = {},
  ) {
    trigger.current = triggerElement
    const view = newView(kind, target, options)
    setWindowState({ openedFor: key, views: [view] })
    loadView(view)
  }

  // A link inside a window: open another window on top of it, so Back can return.
  function openVerse(kind: ContextKind, target: VerseTarget) {
    const view = newView(kind, target)
    setWindowState((current) => (current ? { ...current, views: [...current.views, view] } : current))
    loadView(view)
  }

  function goBack() {
    request.current?.abort()
    setWindowState((current) =>
      current && current.views.length > 1 ? { ...current, views: current.views.slice(0, -1) } : current,
    )
  }

  // Switch Related Verses between "points to" and "pointed to by". The old list stays up until the
  // new one arrives.
  function changeDirection(direction: RelatedDirection) {
    if (currentView === null || currentView.direction === direction) {
      return
    }
    updateView(currentView.id, { direction, errorMessage: '' })
    loadView({ ...currentView, direction })
  }

  // Switch to another commentary. The text on screen stays until the new one arrives.
  function changeCommentary(commentaryId: string) {
    if (currentView === null || (currentView.commentaryId ?? currentView.commentary?.selected) === commentaryId) {
      return
    }
    updateView(currentView.id, { commentaryId, errorMessage: '' })
    loadView({ ...currentView, commentaryId })
  }

  const close = useCallback(() => {
    request.current?.abort()
    setWindowState(null)
    // Put the keyboard focus back on the link that was used, once the page is visible again.
    const element = trigger.current
    window.setTimeout(() => element?.focus(), 0)
  }, [])

  useEffect(() => {
    if (!isShowing) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        close()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isShowing, close])

  return { isShowing, views, currentView, open, openVerse, goBack, changeDirection, changeCommentary, close }
}
