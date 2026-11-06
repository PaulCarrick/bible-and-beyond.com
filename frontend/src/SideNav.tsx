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

// The navigation down the left of the page (a menu under the header on a phone).
function SideNav({ groups, activeView, isOpen, onNavigate }: SideNavProps) {
  return (
    <nav id="side-navigation" className={isOpen ? 'side-nav is-open' : 'side-nav'} aria-label="Main">
      <div className="side-nav-inner">
      {groups.map((group, index) => (
        <div className="side-nav-group" key={group.heading ?? index}>
          {group.heading && <div className="side-nav-heading">{group.heading}</div>}
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
      ))}
      </div>
    </nav>
  )
}

export default SideNav
