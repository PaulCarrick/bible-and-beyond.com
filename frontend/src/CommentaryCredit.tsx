import type { CommentaryOrigin } from './types'

const freeUseBibleApi = 'https://bible.helloao.org'
const publicDomainMark = 'https://creativecommons.org/publicdomain/mark/1.0/'

interface CommentaryCreditProps {
  // The commentary being credited; without it, the credit for the ones from the Free Use Bible API.
  origin?: CommentaryOrigin
}

// The credit for a commentary. The six loaded from the Free Use Bible API are marked Public Domain there (the
// credit is a courtesy); one uploaded in the admin names its own source and licence.
function CommentaryCredit({ origin }: CommentaryCreditProps) {
  if (!origin || origin.source_url === freeUseBibleApi) {
    return (
      <>
        Commentaries are in the public domain (
        <a href={publicDomainMark} target="_blank" rel="noreferrer">
          Public Domain Mark
        </a>
        ). The text comes from the{' '}
        <a href={freeUseBibleApi} target="_blank" rel="noreferrer">
          Free Use Bible API
        </a>{' '}
        and was loaded into this site&rsquo;s database. Spelling and wording are as in the old editions.
      </>
    )
  }
  return (
    <>
      The text comes from{' '}
      {origin.source_url ? (
        <a href={origin.source_url} target="_blank" rel="noreferrer">
          {origin.source_name}
        </a>
      ) : (
        origin.source_name
      )}{' '}
      (
      <a href={origin.license_url} target="_blank" rel="noreferrer">
        {origin.license_url === publicDomainMark ? 'Public Domain Mark' : 'licence'}
      </a>
      ) and was loaded into this site&rsquo;s database.
    </>
  )
}

export default CommentaryCredit
