import type { DevotionalInfo } from './types'

interface DevotionalCreditProps {
  devotional: DevotionalInfo
}

// Where a devotional's text comes from. All four are in the public domain; the credit is a courtesy.
function DevotionalCredit({ devotional }: DevotionalCreditProps) {
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
