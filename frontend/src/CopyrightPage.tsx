import { useEffect, useState } from 'react'
import { fetchCopyrights } from './api'
import CommentaryCredit from './CommentaryCredit'
import CrossReferenceCredit from './CrossReferenceCredit'
import DevotionalCredit from './DevotionalCredit'
import StepBibleCredit from './StepBibleCredit'
import type { Copyright, DevotionalInfo } from './types'

interface CopyrightPageProps {
  onBack: () => void
  devotionals?: DevotionalInfo[]
}

function CopyrightPage({ onBack, devotionals = [] }: CopyrightPageProps) {
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
        Back to Help
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

      <h3>Commentaries</h3>
      <p>
        Matthew Henry, John Gill, Adam Clarke, Jamieson-Fausset-Brown, John Calvin, and Keil and Delitzsch.{' '}
        <CommentaryCredit />
      </p>

      {devotionals.length > 0 && (
        <>
          <h3>Devotionals</h3>
          {devotionals.map((devotional) => (
            <p key={devotional.id}>
              <DevotionalCredit devotional={devotional} />
            </p>
          ))}
        </>
      )}
    </div>
  )
}

export default CopyrightPage
