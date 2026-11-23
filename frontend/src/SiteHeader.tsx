import AccountMenu from './AccountMenu'
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
  // False while "Login required" is on: only an administrator sets up accounts then (Site users).
  canSetUpAccount?: boolean
  onShowNotes: () => void
  onShowLists: () => void
  // The My account page (Account settings in the menu).
  onShowAccount: () => void
  onLogIn: () => void
  onLogOut: () => void
}

// The top of every page: the emblem and the name of the site, on a phone the button for the menu, and at the far
// right the account icon with its menu (AccountMenu.tsx; it replaced the row of account links on 2026-11-23).
function SiteHeader({ title, iconAddress, isMenuOpen, onToggleMenu, onGoHome, user, onSetUpAccount, canSetUpAccount = true, onShowNotes, onShowLists, onShowAccount, onLogIn, onLogOut }: SiteHeaderProps) {
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
      <AccountMenu
        user={user}
        canSetUpAccount={canSetUpAccount}
        onShowAccount={onShowAccount}
        onShowNotes={onShowNotes}
        onShowLists={onShowLists}
        onLogIn={onLogIn}
        onSetUpAccount={onSetUpAccount}
        onLogOut={onLogOut}
      />
    </header>
  )
}

export default SiteHeader
