interface SiteFooterProps {
  // The site's own copyright line, as the administrator has set it (empty shows none).
  copyrightText: string
}

// The bottom of every page: the copyright of the site. The notices and credits for the texts are on the
// Help page.
function SiteFooter({ copyrightText }: SiteFooterProps) {
  if (!copyrightText) {
    return null
  }
  return (
    <footer className="site-footer">
      <p className="site-copyright">{copyrightText}</p>
    </footer>
  )
}

export default SiteFooter
