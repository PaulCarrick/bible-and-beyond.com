interface SiteHeaderProps {
  // On a phone the sidebar is a menu that the button opens and closes.
  isMenuOpen: boolean
  onToggleMenu: () => void
  onGoHome: () => void
}

// The top of every page: the icon and the name of the site, and on a phone the button for the menu.
function SiteHeader({ isMenuOpen, onToggleMenu, onGoHome }: SiteHeaderProps) {
  return (
    <header className="site-header">
      <button
        type="button"
        className="menu-button"
        aria-expanded={isMenuOpen}
        aria-controls="side-navigation"
        onClick={onToggleMenu}
      >
        <span aria-hidden="true">{isMenuOpen ? '✕' : '☰'}</span>
        <span className="visually-hidden">{isMenuOpen ? 'Close the menu' : 'Open the menu'}</span>
      </button>
      <button type="button" className="site-title" onClick={onGoHome}>
        <img className="site-icon" src="/favicon.svg" alt="" width="44" height="44" />
        <span className="site-name">Bible and Beyond</span>
      </button>
      <span className="site-tagline">Read, search and study the Bible</span>
    </header>
  )
}

export default SiteHeader
