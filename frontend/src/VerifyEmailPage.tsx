import { useEffect, useState } from 'react'
import { fetchCurrentUser, verifyEmail } from './api'
import type { AccountUser } from './types'

interface VerifyEmailPageProps {
  token: string
  // Called with whoever is logged in once the address is confirmed, so the page can drop its reminder.
  onVerified: (user: AccountUser | null) => void
}

// A link can be used once, so each one is sent to the server once however many times the page asks
// (React runs an effect twice while developing).
const requests = new Map<string, Promise<void>>()
function verifyOnce(token: string): Promise<void> {
  if (!requests.has(token)) {
    requests.set(token, verifyEmail(token))
  }
  return requests.get(token)!
}

// The page that the link in the confirmation email opens.
function VerifyEmailPage({ token, onVerified }: VerifyEmailPageProps) {
  const [message, setMessage] = useState('Confirming your email address…')
  const [isError, setIsError] = useState(false)

  useEffect(() => {
    let isCurrent = true
    verifyOnce(token)
      .then(() => {
        if (isCurrent) {
          setMessage('Thank you. Your email address is confirmed.')
        }
        return fetchCurrentUser().then(onVerified)
      })
      .catch((error: Error) => {
        if (isCurrent) {
          setIsError(true)
          setMessage(error.message)
        }
      })
    return () => {
      isCurrent = false
    }
  }, [token, onVerified])

  return (
    <div className="account-page">
      <h1>Confirm your email address</h1>
      <p className={isError ? 'error' : undefined} role="status">
        {message}
      </p>
    </div>
  )
}

export default VerifyEmailPage
