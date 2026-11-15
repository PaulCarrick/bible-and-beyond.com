import { useEffect, useState } from 'react'
import { mapFileAddress } from './api'
import type { MapInfo } from './api'
import MapViewer from './MapViewer'
import MapsCredit from './MapsCredit'
import type { VerseInBible } from './verseAddress'

interface MapsPageProps {
  maps: MapInfo[]
  isHidden: boolean
  // A map to show (an address such as /maps?map=pauls-journeys, or a search hit), with a new key each time.
  focus: { id: string; key: number } | null
  onOpenVerse: (verse: VerseInBible) => void
}

// The maps: a card for each with its picture, title and verses, and Open this map, which shows the map viewer
// (zoom and pan, its details and, for a member allowed them, their own notes, pins and routes). The page stays
// mounted, so the map open and where it was zoomed to are kept while another page is open.
function MapsPage({ maps, isHidden, focus, onOpenVerse }: MapsPageProps) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [shownFocusKey, setShownFocusKey] = useState<number | null>(null)
  // A map asked for by an address or a search hit (set while rendering, as React advises for state that follows a prop).
  if (focus && focus.key !== shownFocusKey) {
    setShownFocusKey(focus.key)
    if (maps.some((map) => map.id === focus.id)) {
      setOpenId(focus.id)
    }
  }
  const openMap = maps.find((map) => map.id === openId) ?? null

  useEffect(() => {
    if (!isHidden && openId) {
      window.scrollTo(0, 0)
    }
  }, [openId, isHidden])

  if (openMap) {
    return (
      <div className="welcome maps-page" hidden={isHidden}>
        <MapViewer key={openMap.id} map={openMap} isHidden={isHidden} onBack={() => setOpenId(null)} onOpenVerse={onOpenVerse} />
        <p className="maps-credit">
          <MapsCredit />
        </p>
      </div>
    )
  }

  return (
    <div className="welcome maps-page" hidden={isHidden}>
      <h1>Maps</h1>
      <p>
        Maps of the lands and journeys of the Bible. Open one to zoom in and move about it (a pinch or two fingers on a
        phone), and to read the verses it goes with.
      </p>
      <ul className="map-cards">
        {maps.map((map) => (
          <li key={map.id} className="map-card">
            <button type="button" className="map-card-picture" onClick={() => setOpenId(map.id)} aria-label={`Open the map ${map.title}`}>
              <img src={mapFileAddress(map, 'thumbnail')} alt="" loading="lazy" width={480} height={Math.round((480 * map.height) / map.width)} />
            </button>
            <h2>{map.title}</h2>
            {map.verses_text && <p className="map-card-verses">{map.verses_text}</p>}
            <button type="button" className="primary-button" onClick={() => setOpenId(map.id)}>
              Open this map
            </button>
          </li>
        ))}
      </ul>
      <p className="maps-credit">
        <MapsCredit />
      </p>
    </div>
  )
}

export default MapsPage
