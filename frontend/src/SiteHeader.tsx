import type { AccountUser } from './types'

interface SiteHeaderProps {
  // The name of the site, as the administrator has set it.
  title: string
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
function SiteHeader({ title, isMenuOpen, onToggleMenu, onGoHome, user, onSetUpAccount, onShowNotes, onLogIn, onLogOut }: SiteHeaderProps) {
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
        <img className="site-icon" src="/logo-icon.svg" alt="" width="44" height="44" />
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
            <button type="button" className="link-button" onClick={onSetUpAccount}>
              Set up account
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
