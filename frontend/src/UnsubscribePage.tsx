import { useEffect, useState } from 'react'
import { unsubscribeWithToken } from './api'

interface UnsubscribePageProps {
  token: string
}

// A link can be used once, so each is sent to the server once however many times the page asks.
const requests = new Map<string, Promise<string>>()
function unsubscribeOnce(token: string): Promise<string> {
  if (!requests.has(token)) {
    requests.set(token, unsubscribeWithToken(token))
  }
  return requests.get(token)!
}

// The page that the link at the foot of a devotional email opens: it stops that devotional's emails.
function UnsubscribePage({ token }: UnsubscribePageProps) {
  const [message, setMessage] = useState('Stopping the emails…')
  const [isError, setIsError] = useState(false)

  useEffect(() => {
    let isCurrent = true
    unsubscribeOnce(token)
      .then((name) => isCurrent && setMessage(`Done. You will not get any more emails of ${name}.`))
      .catch((error: Error) => {
        if (isCurrent) {
          setIsError(true)
          setMessage(error.message)
        }
      })
    return () => {
      isCurrent = false
    }
  }, [token])

  return (
    <div className="account-page">
      <h1>Stop the emails</h1>
      <p className={isError ? 'error' : undefined} role="status">
        {message}
      </p>
    </div>
  )
}

export default UnsubscribePage
