import { createContext } from 'react'
import type { AccountUser } from './types'
import type { View } from './views'

// Who is logged in, for the parts of the site that deep inside a window need to know (the notes).
export interface AccountState {
  user: AccountUser | null
  onNavigate: (view: View) => void
}

export const AccountContext = createContext<AccountState>({ user: null, onNavigate: () => undefined })
