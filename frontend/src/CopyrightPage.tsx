import { useEffect, useState } from 'react'
import { fetchCopyrights } from './api'
import CrossReferenceCredit from './CrossReferenceCredit'
import StepBibleCredit from './StepBibleCredit'
import type { Copyright } from './types'

interface CopyrightPageProps {
  onBack: () => void
}

function CopyrightPage({ onBack }: CopyrightPageProps) {
  const [copyrights, setCopyrights] = useState<Copyright[]>([])
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    fetchCopyrights()
      .then(setCopyrights)
      .catch((error) =>
        setErrorMessage(error instanceof Error ? error.message : 'Could not load copyright notices'),
      )
  }, [])

  return (
    <div className="panel copyright-page">
      <button type="button" className="link-button" onClick={onBack}>
        Back to search
      </button>
      <h2>Bible copyright notices</h2>
      <p>
        The NIV, NASB and The Message are provided through{' '}
        <a href="https://api.bible" target="_blank" rel="noreferrer">
          API.Bible
        </a>{' '}
        and used by permission of their rights holders.
      </p>
      {errorMessage && <p className="error">{errorMessage}</p>}
      {copyrights.map((entry) => (
        <section key={entry.code}>
          <h3>
            {entry.name} ({entry.abbreviation})
          </h3>
          <p>{entry.copyright}</p>
          {entry.rights_holder_url && (
            <p>
              <a href={entry.rights_holder_url} target="_blank" rel="noreferrer">
                Rights holder website
              </a>
            </p>
          )}
        </section>
      ))}

      <h3>Cross references</h3>
      <p>
        <CrossReferenceCredit /> Used under the Creative Commons Attribution 4.0 license. The data was
        reformatted for this site.
      </p>

      <h3>Hebrew and Greek words</h3>
      <p>
        <StepBibleCredit /> Used under the Creative Commons Attribution 4.0 license.
      </p>
    </div>
  )
}

export default CopyrightPage
