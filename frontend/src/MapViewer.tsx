import { useContext, useEffect, useId, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { AccountContext } from './AccountContext'
import { deleteMapMark, fetchMapMarks, mapFileAddress, saveMapMark } from './api'
import type { MapInfo, MapMark } from './api'
import { verseButtonProps } from './verseAddress'
import type { VerseInBible } from './verseAddress'

interface MapViewerProps {
  map: MapInfo
  isHidden: boolean
  onBack: () => void
  // Open the Bible reader at a verse on this page (a plain click; Shift, Ctrl or Cmd opens a new tab).
  onOpenVerse: (verse: VerseInBible) => void
}

// The route colours (map_marks.COLOURS); the server refuses any other.
const colours = [
  { value: '#c0392b', name: 'Red' },
  { value: '#1f6fb2', name: 'Blue' },
  { value: '#2e8540', name: 'Green' },
  { value: '#8e44ad', name: 'Purple' },
  { value: '#d35400', name: 'Orange' },
  { value: '#111111', name: 'Black' },
]

type Tool = 'look' | 'pin' | 'route'

// A mark being written or changed: a new one has no id.
interface Draft {
  id: number | null
  kind: MapMark['kind']
  x: number | null
  y: number | null
  points: [number, number][] | null
  name: string
  colour: string
  body: string
  // The addresses of the members it is shared with.
  sharedWith: string[]
}

// A member's note with the verses it names as links to the Bible reader (line breaks kept by the style).
function MarkText({ mark, onOpenVerse }: { mark: MapMark; onOpenVerse: (verse: VerseInBible) => void }) {
  const pieces = []
  let last = 0
  for (const [start, end, code] of mark.references) {
    const [book, chapter, verse] = code.split(':').map(Number)
    const target = { translation: 'BSB', book, chapter, verse }
    pieces.push(mark.body.slice(last, start))
    pieces.push(
      <button key={start} type="button" className="link-button reference-link" {...verseButtonProps(target, () => onOpenVerse(target))}>
        {mark.body.slice(start, end)}
      </button>,
    )
    last = end
  }
  pieces.push(mark.body.slice(last))
  return <p className="map-mark-text">{pieces}</p>
}

// One map: zoom and pan (mouse wheel, pinch, the + and − buttons or the keyboard), its description, source and
// verses, and, for a member an administrator allowed (use_maps), their own notes, pins and routes drawn over it.
//
// The picture is shown with Leaflet in a flat coordinate system the size of the picture. A member's marks are
// kept as fractions of the picture (0 to 1 across and down), so the shared picture is never copied; only these
// few numbers are saved, and only the member sees them.
function MapViewer({ map, isHidden, onBack, onOpenVerse }: MapViewerProps) {
  const { user, onNavigate } = useContext(AccountContext)
  const canMark = user?.use_maps === true
  const containerRef = useRef<HTMLDivElement | null>(null)
  const leafletRef = useRef<L.Map | null>(null)
  const marksLayerRef = useRef<L.LayerGroup | null>(null)
  const [marks, setMarks] = useState<MapMark[]>([])
  const [tool, setTool] = useState<Tool>('look')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isFullScreen, setIsFullScreen] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const noteId = useId()
  const nameId = useId()
  const colourId = useId()
  const shareId = useId()
  const [shareAddress, setShareAddress] = useState('')
  // The click handler is set once, so it reads the tool through this.
  const toolRef = useRef(tool)
  useEffect(() => {
    toolRef.current = tool
    // While placing a pin or a route's points, a double click adds points rather than zooming.
    if (tool === 'look') {
      leafletRef.current?.doubleClickZoom.enable()
    } else {
      leafletRef.current?.doubleClickZoom.disable()
    }
  }, [tool])

  const width = map.width
  const height = map.height
  const toPlace = (x: number, y: number) => L.latLng(height * (1 - y), width * x)

  // The map itself, made again when another map is shown.
  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }
    const bounds = L.latLngBounds([0, 0], [map.height, map.width])
    const leaflet = L.map(container, {
      crs: L.CRS.Simple,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 120,
      attributionControl: false,
      maxBoundsViscosity: 0.8,
    })
    L.imageOverlay(mapFileAddress(map, 'display'), bounds, { alt: map.title }).addTo(leaflet)
    // The zoom limits follow the size of the box the map is shown in, whatever the device: zoomed out a little past
    // the whole map, and in to four times the picture's pixels or two steps past the whole map on a large screen.
    // (getBoundsZoom and fitBounds keep within the limits, so they are opened wide to measure.)
    function fitLimits() {
      leaflet.setMinZoom(-20)
      leaflet.setMaxZoom(20)
      const fitZoom = leaflet.getBoundsZoom(bounds)
      leaflet.setMinZoom(fitZoom - 1)
      leaflet.setMaxZoom(Math.max(2, fitZoom + 2))
      return fitZoom
    }
    fitLimits()
    leaflet.fitBounds(bounds)
    // Measured again whenever the box changes size: a phone turned, a window resized, the sidebar menu, full screen,
    // or the page shown again after being hidden.
    const resizeObserver = new ResizeObserver(() => {
      if (container.clientWidth === 0 || container.clientHeight === 0) {
        return
      }
      leaflet.invalidateSize()
      const wasWhole = leaflet.getZoom() <= leaflet.getMinZoom() + 1.01
      fitLimits()
      if (wasWhole) {
        leaflet.fitBounds(bounds)
      }
    })
    resizeObserver.observe(container)
    leaflet.setMaxBounds(bounds.pad(0.25))
    marksLayerRef.current = L.layerGroup().addTo(leaflet)
    leaflet.on('click', (event: L.LeafletMouseEvent) => {
      if (!bounds.contains(event.latlng)) {
        return
      }
      const x = Math.min(1, Math.max(0, event.latlng.lng / map.width))
      const y = Math.min(1, Math.max(0, 1 - event.latlng.lat / map.height))
      if (toolRef.current === 'pin') {
        setDraft({ id: null, kind: 'pin', x, y, points: null, name: '', colour: colours[0].value, body: '', sharedWith: [] })
        setTool('look')
      } else if (toolRef.current === 'route') {
        // From the draft as it is now (quick clicks come before the page has drawn the last one). A route being
        // changed keeps its id, so points are added to its end.
        setDraft((current) => {
          const route = current?.kind === 'route' ? current : null
          return {
            id: route?.id ?? null,
            kind: 'route',
            x: null,
            y: null,
            points: [...(route?.points ?? []), [x, y]],
            name: route?.name ?? '',
            colour: route?.colour ?? colours[0].value,
            body: route?.body ?? '',
            sharedWith: route?.sharedWith ?? [],
          }
        })
      }
    })
    leafletRef.current = leaflet
    return () => {
      resizeObserver.disconnect()
      leaflet.remove()
      leafletRef.current = null
      marksLayerRef.current = null
    }
  }, [map])

  // Leaflet measures its box: when the page is shown again or goes full screen, it is told the box changed.
  useEffect(() => {
    if (!isHidden) {
      leafletRef.current?.invalidateSize()
    }
  }, [isHidden, isFullScreen])

  useEffect(() => {
    if (!isFullScreen) {
      return
    }
    function leave(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsFullScreen(false)
      }
    }
    window.addEventListener('keydown', leave)
    return () => window.removeEventListener('keydown', leave)
  }, [isFullScreen])

  // The member's own marks on this map.
  useEffect(() => {
    if (!canMark) {
      return
    }
    const request = new AbortController()
    fetchMapMarks(map.id, request.signal)
      .then(setMarks)
      .catch((error: Error) => {
        if (!request.signal.aborted) {
          setMessage(error.message)
        }
      })
    return () => request.abort()
  }, [map.id, canMark])

  // Nothing of the last visitor's stays after logging out or in as someone else (the effect above reloads).
  const userId = user?.id ?? null
  const [shownUserId, setShownUserId] = useState(userId)
  if (shownUserId !== userId) {
    setShownUserId(userId)
    setMarks([])
    setDraft(null)
    setTool('look')
    setSelectedId(null)
  }

  // The pins and routes drawn over the map; the one being changed is drawn from the draft.
  useEffect(() => {
    const layer = marksLayerRef.current
    if (!layer) {
      return
    }
    layer.clearLayers()
    // While placing, a click on a pin or route goes to the map beneath (a route can start at a pin).
    const isPlacing = tool !== 'look'
    const shown = marks.filter((mark) => mark.id !== draft?.id)
    const drawn: (MapMark | Draft)[] = draft ? [...shown, draft] : shown
    for (const mark of drawn) {
      const isDraft = mark === draft
      const isSelected = !isDraft && 'references' in mark && mark.id === selectedId
      // Shared with this member by someone else: drawn in its own style, and never changed here.
      const isOthers = 'is_mine' in mark && !mark.is_mine
      if (mark.kind === 'pin' && mark.x !== null && mark.y !== null) {
        const marker = L.marker(toPlace(mark.x, mark.y), {
          icon: L.divIcon({
            className: `map-pin${isSelected || isDraft ? ' is-selected' : ''}${isOthers ? ' is-others' : ''}`,
            iconSize: [24, 24],
            iconAnchor: [12, 24],
          }),
          draggable: isDraft,
          interactive: isDraft || !isPlacing,
          keyboard: false,
          title: `${isOthers && 'author' in mark ? `${mark.author}: ` : ''}${mark.body ? mark.body.slice(0, 80) : 'Pin'}`,
        })
        if (isDraft) {
          marker.on('dragend', () => {
            const place = marker.getLatLng()
            setDraft((current) =>
              current ? { ...current, x: Math.min(1, Math.max(0, place.lng / width)), y: Math.min(1, Math.max(0, 1 - place.lat / height)) } : current,
            )
          })
        } else if ('references' in mark) {
          marker.on('click', () => setSelectedId(mark.id))
        }
        marker.addTo(layer)
      } else if (mark.kind === 'route' && mark.points && mark.points.length > 0) {
        const line = L.polyline(
          mark.points.map(([x, y]) => toPlace(x, y)),
          {
            color: mark.colour ?? colours[0].value,
            weight: isSelected || isDraft ? 6 : isOthers ? 3 : 4,
            dashArray: isDraft ? '8 6' : isOthers ? '2 6' : undefined,
            opacity: 0.9,
            interactive: !isDraft && !isPlacing,
          },
        )
        if (!isDraft && 'references' in mark) {
          line.on('click', () => setSelectedId(mark.id))
        }
        line.addTo(layer)
        if (isDraft && draft.id !== null && !isPlacing) {
          // A route being changed: each point is a handle that can be dragged to a new place, or taken out with a
          // right-click (a long press on a phone) while the route keeps two. Between two points a smaller, paler handle
          // adds a point there: drag it to where the new point goes, or click or tap it to add one halfway.
          const toFraction = (place: L.LatLng): [number, number] => [
            Math.min(1, Math.max(0, place.lng / width)),
            Math.min(1, Math.max(0, 1 - place.lat / height)),
          ]
          const points = mark.points
          points.forEach(([x, y], index) => {
            const handle = L.marker(toPlace(x, y), {
              icon: L.divIcon({ className: 'map-route-handle', iconSize: [16, 16], iconAnchor: [8, 8] }),
              draggable: true,
              keyboard: false,
              title: `Point ${index + 1}: drag to move it${points.length > 2 ? '; right-click or long-press to take it out' : ''}`,
            })
            handle.on('dragend', () => {
              const moved = toFraction(handle.getLatLng())
              setDraft((current) =>
                current?.points ? { ...current, points: current.points.map((point, at) => (at === index ? moved : point)) } : current,
              )
            })
            handle.on('contextmenu', (event: L.LeafletMouseEvent) => {
              L.DomEvent.preventDefault(event.originalEvent)
              setDraft((current) =>
                current?.points && current.points.length > 2 ? { ...current, points: current.points.filter((_, at) => at !== index) } : current,
              )
            })
            handle.addTo(layer)
            if (index === points.length - 1) {
              return
            }
            const [nextX, nextY] = points[index + 1]
            const halfway: [number, number] = [(x + nextX) / 2, (y + nextY) / 2]
            const insert = (point: [number, number]) =>
              setDraft((current) =>
                current?.points ? { ...current, points: [...current.points.slice(0, index + 1), point, ...current.points.slice(index + 1)] } : current,
              )
            const between = L.marker(toPlace(...halfway), {
              icon: L.divIcon({ className: 'map-route-handle is-between', iconSize: [12, 12], iconAnchor: [6, 6] }),
              draggable: true,
              keyboard: false,
              title: `Add a point between points ${index + 1} and ${index + 2}: drag it into place, or click to add one halfway`,
            })
            let wasDragged = false
            between.on('dragstart', () => {
              wasDragged = true
            })
            between.on('dragend', () => insert(toFraction(between.getLatLng())))
            between.on('click', () => {
              if (!wasDragged) {
                insert(halfway)
              }
            })
            between.addTo(layer)
          })
        } else if (isDraft) {
          for (const [x, y] of mark.points) {
            L.circleMarker(toPlace(x, y), { radius: 4, color: mark.colour ?? colours[0].value, fillOpacity: 1, interactive: false }).addTo(layer)
          }
        }
      }
    }
    // toPlace depends only on the map's size, which the map effect covers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marks, draft, selectedId, map, tool])

  function startPin() {
    setDraft(null)
    setSelectedId(null)
    setMessage('Click or tap the map where the pin goes.')
    setTool('pin')
  }

  function startRoute() {
    setDraft(null)
    setSelectedId(null)
    setMessage('Click or tap the map at each point of the route, in order, then press Finish the route.')
    setTool('route')
  }

  function startNote() {
    setTool('look')
    setSelectedId(null)
    setMessage('')
    setDraft({ id: null, kind: 'note', x: null, y: null, points: null, name: '', colour: colours[0].value, body: '', sharedWith: [] })
  }

  function edit(mark: MapMark) {
    setTool('look')
    setMessage(
      mark.kind === 'pin'
        ? 'Drag the pin to move it.'
        : mark.kind === 'route'
          ? 'Drag a point of the route to move it, or a small point between two to add one there (a click adds one halfway). Right-click or long-press a point to take it out.'
          : '',
    )
    setSelectedId(mark.id)
    setDraft({
      id: mark.id,
      kind: mark.kind,
      x: mark.x,
      y: mark.y,
      points: mark.points,
      name: mark.name,
      colour: mark.colour ?? colours[0].value,
      body: mark.body,
      sharedWith: mark.shared_with.map((member) => member.email),
    })
  }

  function cancel() {
    setDraft(null)
    setTool('look')
    setMessage('')
  }

  async function save() {
    if (!draft) {
      return
    }
    setIsSaving(true)
    setMessage('')
    try {
      const saved = await saveMapMark(map.id, draft.id, {
        kind: draft.kind,
        x: draft.x,
        y: draft.y,
        points: draft.points,
        name: draft.name,
        colour: draft.kind === 'route' ? draft.colour : null,
        body: draft.body,
        shared_with: draft.sharedWith,
      })
      setMarks((current) => (draft.id === null ? [...current, saved] : current.map((mark) => (mark.id === saved.id ? saved : mark))))
      setDraft(null)
      setTool('look')
      setSelectedId(saved.id)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'It could not be saved.')
    } finally {
      setIsSaving(false)
    }
  }

  async function remove(markId: number) {
    setMessage('')
    try {
      await deleteMapMark(markId)
      setMarks((current) => current.filter((mark) => mark.id !== markId))
      setConfirmDeleteId(null)
      setSelectedId(null)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'It could not be deleted.')
    }
  }

  // Bring a pin or route into view and mark it.
  function show(mark: MapMark) {
    setSelectedId(mark.id)
    const leaflet = leafletRef.current
    if (!leaflet) {
      return
    }
    if (mark.kind === 'pin' && mark.x !== null && mark.y !== null) {
      leaflet.panTo(toPlace(mark.x, mark.y))
    } else if (mark.kind === 'route' && mark.points) {
      leaflet.fitBounds(L.latLngBounds(mark.points.map(([x, y]) => toPlace(x, y))), { padding: [30, 30] })
    }
    containerRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  const isDrawingRoute = tool === 'route'
  const routePointCount = draft?.kind === 'route' ? (draft.points?.length ?? 0) : 0
  const kindWords = { note: 'Note', pin: 'Pin', route: 'Route' }
  const ownMarks = marks.filter((mark) => mark.is_mine)
  const pins = ownMarks.filter((mark) => mark.kind === 'pin')
  const routes = ownMarks.filter((mark) => mark.kind === 'route')
  const notes = ownMarks.filter((mark) => mark.kind === 'note')
  // What other members shared with this one, read-only.
  const sharedWithMe = marks.filter((mark) => !mark.is_mine)
  // Addresses already used, offered when sharing again.
  const knownAddresses = [...new Set(ownMarks.flatMap((mark) => mark.shared_with.map((member) => member.email)))]

  function addShare() {
    const address = shareAddress.trim().toLowerCase()
    if (!draft || address === '') {
      return
    }
    if (!draft.sharedWith.includes(address)) {
      setDraft({ ...draft, sharedWith: [...draft.sharedWith, address] })
    }
    setShareAddress('')
  }

  function markItem(mark: MapMark) {
    const isEditing = draft?.id === mark.id
    return (
      <li key={mark.id} className={mark.id === selectedId ? 'map-mark is-selected' : 'map-mark'}>
        <div className="map-mark-heading">
          {mark.kind === 'route' && <span className="map-route-swatch" style={{ background: mark.colour ?? undefined }} aria-hidden="true" />}
          {mark.kind === 'pin' && <span className="map-pin-symbol" aria-hidden="true" />}
          <strong>{mark.kind === 'route' ? mark.name : mark.kind === 'pin' ? 'Pin' : 'Note'}</strong>
          {!mark.is_mine && <span className="map-mark-author">from {mark.author}</span>}
          <span className="map-mark-date">{new Date(mark.updated_at).toLocaleDateString()}</span>
        </div>
        {mark.body && <MarkText mark={mark} onOpenVerse={onOpenVerse} />}
        {mark.is_mine && mark.shared_with.length > 0 && (
          <p className="map-mark-shared">Shared with {mark.shared_with.map((member) => `${member.name} (${member.email})`).join(', ')}</p>
        )}
        {!mark.is_mine && mark.kind !== 'note' && (
          <div className="conversation-actions">
            <button type="button" className="secondary-button small-button" onClick={() => show(mark)}>
              Show on the map
            </button>
          </div>
        )}
        {mark.is_mine && !isEditing && (
          <div className="conversation-actions">
            {mark.kind !== 'note' && (
              <button type="button" className="secondary-button small-button" onClick={() => show(mark)}>
                Show on the map
              </button>
            )}
            <button type="button" className="secondary-button small-button" onClick={() => edit(mark)}>
              Edit
            </button>
            {confirmDeleteId === mark.id ? (
              <>
                <span>Delete this {kindWords[mark.kind].toLowerCase()}?</span>
                <button type="button" className="secondary-button small-button danger-button" onClick={() => remove(mark.id)}>
                  Yes, delete it
                </button>
                <button type="button" className="secondary-button small-button" onClick={() => setConfirmDeleteId(null)}>
                  Cancel
                </button>
              </>
            ) : (
              <button type="button" className="secondary-button small-button" onClick={() => setConfirmDeleteId(mark.id)}>
                Delete
              </button>
            )}
          </div>
        )}
      </li>
    )
  }

  return (
    <div className="map-viewer">
      <div className="map-viewer-top">
        <button type="button" className="secondary-button" onClick={onBack}>
          ← All maps
        </button>
      </div>
      <h1>{map.title}</h1>

      <div className={isFullScreen ? 'map-frame is-full-screen' : 'map-frame'}>
        <div className="map-toolbar">
          {canMark && (
            <>
              <button type="button" className={tool === 'pin' ? 'primary-button' : 'secondary-button'} onClick={startPin} disabled={isSaving}>
                Drop a pin
              </button>
              <button type="button" className={isDrawingRoute ? 'primary-button' : 'secondary-button'} onClick={startRoute} disabled={isSaving}>
                Trace a route
              </button>
              <button type="button" className="secondary-button" onClick={startNote} disabled={isSaving}>
                Add a note
              </button>
            </>
          )}
          <button type="button" className="secondary-button map-full-screen-button" onClick={() => setIsFullScreen(!isFullScreen)}>
            {isFullScreen ? 'Leave full screen' : 'Full screen'}
          </button>
        </div>
        {isDrawingRoute && (
          <div className="map-route-bar" role="status">
            <span>
              {routePointCount === 0 ? 'Click or tap the map at the first point.' : `${routePointCount} point${routePointCount === 1 ? '' : 's'}.`}
            </span>
            <button
              type="button"
              className="secondary-button small-button"
              disabled={routePointCount === 0}
              onClick={() => setDraft((current) => (current?.points ? { ...current, points: current.points.slice(0, -1) } : current))}
            >
              Undo the last point
            </button>
            <button type="button" className="primary-button small-button" disabled={routePointCount < 2} onClick={() => { setTool('look'); setMessage('') }}>
              Finish the route
            </button>
            <button type="button" className="secondary-button small-button" onClick={cancel}>
              Cancel
            </button>
          </div>
        )}
        <div
          ref={containerRef}
          className={tool === 'look' ? 'map-canvas' : 'map-canvas is-placing'}
          role="region"
          aria-label={`The map ${map.title}: drag to move it, and use the + and − buttons, the mouse wheel or a pinch to zoom.`}
        />
      </div>
      {message && <p className="map-message" role="status">{message}</p>}

      {draft && tool === 'look' && (
        <div className="map-mark-form">
          <h2>{draft.id === null ? `New ${kindWords[draft.kind].toLowerCase()}` : `Change the ${kindWords[draft.kind].toLowerCase()}`}</h2>
          {draft.kind === 'route' && (
            <div className="map-form-row">
              <label htmlFor={nameId}>Name</label>
              <input id={nameId} type="text" maxLength={100} value={draft.name} placeholder="Route" onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              <label htmlFor={colourId}>Colour</label>
              <select id={colourId} value={draft.colour} onChange={(event) => setDraft({ ...draft, colour: event.target.value })}>
                {colours.map((colour) => (
                  <option key={colour.value} value={colour.value}>
                    {colour.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <label htmlFor={noteId}>{draft.kind === 'note' ? 'Note' : 'Note (optional)'}</label>
          <textarea
            id={noteId}
            rows={4}
            maxLength={5000}
            value={draft.body}
            onChange={(event) => setDraft({ ...draft, body: event.target.value })}
            placeholder="Verses such as Acts 13:4 become links."
          />
          {draft.kind === 'route' && draft.id !== null && (
            <div className="conversation-actions">
              <span>{draft.points?.length ?? 0} points.</span>
              <button
                type="button"
                className="secondary-button small-button"
                onClick={() => {
                  setMessage('Click or tap the map to add points to the end of the route, then press Finish the route.')
                  setTool('route')
                }}
              >
                Add points at the end
              </button>
              <button
                type="button"
                className="secondary-button small-button"
                disabled={(draft.points?.length ?? 0) <= 2}
                onClick={() => setDraft({ ...draft, points: draft.points ? draft.points.slice(0, -1) : null })}
              >
                Remove the last point
              </button>
            </div>
          )}
          <fieldset className="map-share">
            <legend>Share with (optional)</legend>
            <p className="map-share-hint">
              Only you see it unless you add members here. Type the email address of another member who can use the maps;
              they will see it, but not change it.
            </p>
            {draft.sharedWith.length > 0 && (
              <ul className="map-share-list">
                {draft.sharedWith.map((address) => (
                  <li key={address}>
                    {address}{' '}
                    <button
                      type="button"
                      className="secondary-button small-button"
                      aria-label={`Stop sharing with ${address}`}
                      onClick={() => setDraft({ ...draft, sharedWith: draft.sharedWith.filter((each) => each !== address) })}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="map-form-row">
              <label htmlFor={shareId} className="visually-hidden">
                Email address of a member to share with
              </label>
              <input
                id={shareId}
                type="email"
                list={`${shareId}-known`}
                value={shareAddress}
                placeholder="name@example.com"
                onChange={(event) => setShareAddress(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    addShare()
                  }
                }}
              />
              <datalist id={`${shareId}-known`}>
                {knownAddresses.map((address) => (
                  <option key={address} value={address} />
                ))}
              </datalist>
              <button type="button" className="secondary-button small-button" onClick={addShare} disabled={shareAddress.trim() === ''}>
                Add
              </button>
            </div>
          </fieldset>
          <div className="conversation-actions">
            <button type="button" className="primary-button" onClick={save} disabled={isSaving || (draft.kind === 'note' && draft.body.trim() === '')}>
              {isSaving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="secondary-button" onClick={cancel} disabled={isSaving}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="map-details">
        {map.description && <p className="map-description">{map.description}</p>}
        {map.verses.length > 0 && (
          <p className="map-verses">
            <strong>Verses: </strong>
            {map.verses.map((verse, index) => {
              const target = { translation: 'BSB', book: verse.book_number, chapter: verse.chapter, verse: verse.verse }
              return (
                <span key={verse.label}>
                  {index > 0 && '; '}
                  <button type="button" className="link-button reference-link" {...verseButtonProps(target, () => onOpenVerse(target))}>
                    {verse.label}
                  </button>
                </span>
              )
            })}
          </p>
        )}
        {map.source && <p className="map-source">{map.source}</p>}
      </div>

      <section className="map-layer" aria-label="Your notes, pins and routes">
        <h2>Your notes, pins and routes</h2>
        {!user && (
          <p>
            Members can add their own notes, pins and routes to the maps, and share them with members they choose.{' '}
            <button type="button" className="link-button" onClick={() => onNavigate('login')}>
              Log in
            </button>
          </p>
        )}
        {user && !canMark && (
          <p>Members an administrator has invited can add their own notes, pins and routes here. To ask, use the Contact page.</p>
        )}
        {canMark && ownMarks.length === 0 && (
          <p>You have none on this map yet. Use Drop a pin, Trace a route or Add a note above. Only you see them, unless you share one with members you choose.</p>
        )}
        {canMark && pins.length > 0 && (
          <>
            <h3>Pins</h3>
            <ul className="map-mark-list">{pins.map(markItem)}</ul>
          </>
        )}
        {canMark && routes.length > 0 && (
          <>
            <h3>Routes</h3>
            <ul className="map-mark-list">{routes.map(markItem)}</ul>
          </>
        )}
        {canMark && notes.length > 0 && (
          <>
            <h3>Notes</h3>
            <ul className="map-mark-list">{notes.map(markItem)}</ul>
          </>
        )}
        {canMark && sharedWithMe.length > 0 && (
          <>
            <h3>Shared with you</h3>
            <ul className="map-mark-list">{sharedWithMe.map(markItem)}</ul>
          </>
        )}
      </section>
    </div>
  )
}

export default MapViewer
