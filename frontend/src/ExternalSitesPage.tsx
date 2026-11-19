import type { ExternalSite } from './api'

interface ExternalSitesPageProps {
  sites: ExternalSite[]
}

// The external sites the administrators chose to show (the Drupal "External sites" page, "Show it in the site's
// sidebar"; added 2026-11-19 at the owner's request): each a link that opens the site in a new tab, so this site stays
// open. Only their names and addresses reach the site; the sidebar group shows only when there are some.
function ExternalSitesPage({ sites }: ExternalSitesPageProps) {
  return (
    <div className="welcome external-sites-page">
      <h1>External sites</h1>
      <p>
        Other sites we use and recommend. Each opens in a new tab, so this site stays open in this one. They are not
        part of this site: if one asks you to sign in, that is with your own account there.
      </p>
      {/* Reached by its address when none are shown (the sidebar has no entry then). */}
      {sites.length === 0 && <p>There are no external sites at the moment.</p>}
      <ul className="external-sites-list">
        {sites.map((site) => (
          <li key={site.address}>
            <a href={site.address} target="_blank" rel="noopener noreferrer" title={`Open ${site.name} in a new tab`}>
              {site.name}
            </a>{' '}
            <span className="external-site-host">({site.host}, opens in a new tab)</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ExternalSitesPage
