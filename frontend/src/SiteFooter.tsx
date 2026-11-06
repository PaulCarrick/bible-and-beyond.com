import { useEffect, useState } from 'react'
import { fetchCopyrights } from './api'
import type { Copyright } from './types'

interface SiteFooterProps {
  onShowCopyrightNotices: () => void
}

// The bottom of every page: the copyright notice of each Bible that is licensed to us, the credits for
// the data that asks for them, and the copyright of the site.
function SiteFooter({ onShowCopyrightNotices }: SiteFooterProps) {
  const [copyrights, setCopyrights] = useState<Copyright[]>([])

  // The notices come from API.Bible with the text (the server keeps them for a day). If they cannot be
  // had, the footer still says where the Bibles come from and links to the full notices.
  useEffect(() => {
    fetchCopyrights()
      .then(setCopyrights)
      .catch(() => setCopyrights([]))
  }, [])

  return (
    <footer className="site-footer">
      <div className="footer-notices">
        <p>
          <strong>Licensed Bibles.</strong> Scripture for the NIV, NASB and The Message is provided through{' '}
          <a href="https://api.bible" target="_blank" rel="noreferrer">
            API.Bible
          </a>
          .{' '}
          <button type="button" className="link-button" onClick={onShowCopyrightNotices}>
            Bible copyright notices
          </button>
        </p>
        {copyrights.length > 0 && (
          <ul className="footer-copyrights">
            {copyrights.map((copyright) => (
              <li key={copyright.code}>
                <strong>{copyright.code}</strong> {copyright.copyright}
              </li>
            ))}
          </ul>
        )}
        <p>
          <strong>Credits.</strong> Hebrew and Greek data from{' '}
          <a href="https://www.stepbible.org" target="_blank" rel="noreferrer">
            STEP Bible
          </a>{' '}
          (
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
            CC BY 4.0
          </a>
          ). Cross references from{' '}
          <a href="https://www.openbible.info/labs/cross-references/" target="_blank" rel="noreferrer">
            OpenBible.info
          </a>{' '}
          (
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
            CC BY 4.0
          </a>
          ). The other Bibles, the commentaries and the devotionals are in the public domain.
        </p>
      </div>
      <p className="site-copyright">Copyright © 2026 by Paul Carrick. All Rights Reserved.</p>
    </footer>
  )
}

export default SiteFooter
