import { useState } from 'react'
import type { View } from './views'

export interface NavGroup {
  // A small heading over the entries; none for the first group.
  heading?: string
  entries: { view: View; label: string }[]
}

interface SideNavProps {
  groups: NavGroup[]
  activeView: View
  isOpen: boolean
  onNavigate: (view: View) => void
}

function groupHeadingOf(groups: NavGroup[], view: View): string | undefined {
  return groups.find((group) => group.entries.some((entry) => entry.view === view))?.heading
}

// The navigation down the left of the page (a menu under the header on a phone).
//
// A group with a heading opens and closes when its heading is clicked; they all start closed (the owner's choice,
// 2026-11-14), except the group of the page being shown, which opens whenever that page is reached, so the page
// is always marked. A group without a heading (Welcome, Search everything) is always open. What is open is kept
// only while the page is open.
function SideNav({ groups, activeView, isOpen, onNavigate }: SideNavProps) {
  const [openHeadings, setOpenHeadings] = useState<Set<string>>(() => {
    const heading = groupHeadingOf(groups, activeView)
    return new Set(heading ? [heading] : [])
  })
  // The page last opened, so its group is opened once each time another page is reached (set while rendering, as
  // React advises for state that follows a prop).
  const [shownView, setShownView] = useState(activeView)
  if (shownView !== activeView) {
    setShownView(activeView)
    const heading = groupHeadingOf(groups, activeView)
    if (heading && !openHeadings.has(heading)) {
      setOpenHeadings(new Set([...openHeadings, heading]))
    }
  }

  function toggle(heading: string) {
    setOpenHeadings((current) => {
      const next = new Set(current)
      if (next.has(heading)) {
        next.delete(heading)
      } else {
        next.add(heading)
      }
      return next
    })
  }

  return (
    <nav id="side-navigation" className={isOpen ? 'side-nav is-open' : 'side-nav'} aria-label="Main">
      <div className="side-nav-inner">
        {groups.map((group, index) => {
          const isGroupOpen = !group.heading || openHeadings.has(group.heading)
          const entriesId = `side-nav-group-${index}`
          return (
            <div className="side-nav-group" key={group.heading ?? index}>
              {group.heading && (
                <button
                  type="button"
                  className="side-nav-heading"
                  aria-expanded={isGroupOpen}
                  aria-controls={entriesId}
                  onClick={() => toggle(group.heading as string)}
                >
                  <span className="side-nav-arrow" aria-hidden="true">
                    ▶
                  </span>
                  {group.heading}
                </button>
              )}
              <div id={entriesId} hidden={!isGroupOpen}>
                {group.entries.map((entry) => (
                  <button
                    type="button"
                    key={entry.view}
                    className={entry.view === activeView ? 'side-nav-item active' : 'side-nav-item'}
                    aria-current={entry.view === activeView ? 'page' : undefined}
                    onClick={() => onNavigate(entry.view)}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </nav>
  )
}

export default SideNav
