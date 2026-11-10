import type { DevotionalInfo } from './types'

interface DevotionalCreditProps {
  devotional: DevotionalInfo
}

// Where a devotional's text comes from. The old texts are in the public domain and the credit is a courtesy;
// a text that is not (the modern wording of the Apostles' Creed) has its own credit line instead.
function DevotionalCredit({ devotional }: DevotionalCreditProps) {
  if (devotional.credit) {
    return <>{devotional.credit}</>
  }
  return (
    <>
      <em>{devotional.name}</em> by {devotional.author}
      {devotional.translator ? ` (${devotional.translator})` : ''} is in the public domain. The text comes from the{' '}
      <a href={devotional.source_url} target="_blank" rel="noreferrer">
        {devotional.source_name}
      </a>{' '}
      and was loaded into this site&rsquo;s database. Spelling and wording are as in the old editions.
    </>
  )
}

export default DevotionalCredit
