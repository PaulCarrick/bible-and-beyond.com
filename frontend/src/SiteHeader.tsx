import type { AccountUser } from './types'

interface SiteHeaderProps {
  // The name of the site, as the administrator has set it.
  title: string
  // The emblem beside the name: the site's own (/logo-icon.svg) or one uploaded on the Site settings screen;
  // null while the settings are loading (its place is kept empty, so a replaced emblem never flashes the old one).
  iconAddress: string | null
  // On a phone the sidebar is a menu that the button opens and closes.
  isMenuOpen: boolean
  onToggleMenu: () => void
  onGoHome: () => void
  // Who is logged in (nobody, unless they chose to).
  user: AccountUser | null
  onSetUpAccount: () => void
  onShowNotes: () => void
  onLogIn: () => void
  onLogOut: () => void
}

// The top of every page: the emblem and the name of the site, and on a phone the button for the menu.
function SiteHeader({ title, iconAddress, isMenuOpen, onToggleMenu, onGoHome, user, onSetUpAccount, onShowNotes, onLogIn, onLogOut }: SiteHeaderProps) {
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
        {iconAddress ? (
          <img
            className={iconAddress === '/logo-icon.svg' ? 'site-icon' : 'site-icon is-uploaded'}
            src={iconAddress}
            alt=""
            width="44"
            height="44"
          />
        ) : (
          <span className="site-icon" aria-hidden="true" />
        )}
        <span className="site-name">{title}</span>
      </button>
      <span className="site-tagline">Read, search and study the Bible</span>
      <nav className="site-account" aria-label="Account">
        {user ? (
          <>
            <span className="site-account-email" title={user.email}>
              {user.email}
            </span>
            <button type="button" className="link-button" onClick={onShowNotes}>
              My notes
            </button>
            <button type="button" className="link-button" onClick={onLogOut}>
              Log out
            </button>
          </>
        ) : (
          <>
            <button type="button" className="link-button" aria-label="Set up account" onClick={onSetUpAccount}>
              Set up<span className="phone-hidden"> account</span>
            </button>
            <button type="button" className="link-button" onClick={onLogIn}>
              Log in
            </button>
          </>
        )}
      </nav>
    </header>
  )
}

export default SiteHeader
