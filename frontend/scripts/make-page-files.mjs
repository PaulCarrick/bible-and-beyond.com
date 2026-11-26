// Run after `vite build`. Every address of the site is served by the same index.html, so a search engine reading
// the HTML (before the app's JavaScript runs) used to see one page with no words, under one title, at every address.
// This writes a copy of dist/index.html for each public page in src/pageInfo.json, with the page's own title,
// description, canonical address and a short paragraph about it, as dist/pages/<path>.html; and gives the welcome
// page's own in dist/index.html. nginx serves dist/pages/<path>.html for <path> when it exists (deploy/nginx/
// bible-and-beyond-app.conf). The app replaces the paragraph as soon as it starts.
//
// SITE_NAME (the site's title) and SITE_ORIGIN (https://name, no slash at the end) come from the environment;
// deploy/deploy.sh passes the server's. Without SITE_ORIGIN no canonical link is written.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendFolder = join(dirname(fileURLToPath(import.meta.url)), '..')
const distFolder = join(frontendFolder, 'dist')
const pages = JSON.parse(readFileSync(join(frontendFolder, 'src', 'pageInfo.json'), 'utf8'))
const siteName = (process.env.SITE_NAME || '').trim() || 'Bible and Beyond'
const siteOrigin = (process.env.SITE_ORIGIN || '').trim().replace(/\/+$/, '')

if (siteOrigin && !/^https?:\/\/[a-z0-9.-]+(:\d+)?$/i.test(siteOrigin)) {
  throw new Error(`SITE_ORIGIN must be like https://example.org, not ${siteOrigin}`)
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const template = readFileSync(join(distFolder, 'index.html'), 'utf8')
if (!template.includes('<title>') || !template.includes('<div id="root"></div>')) {
  throw new Error('dist/index.html does not have the <title> and empty root this script fills in')
}

function pageHtml(page) {
  const title = page.title ? `${page.title} – ${siteName}` : siteName
  const heading = page.title || siteName
  const headLines = [
    `<title>${escapeHtml(title)}</title>`,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:title" content="${escapeHtml(title)}" />`,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:site_name" content="${escapeHtml(siteName)}" />`,
    `<meta property="og:type" content="website" />`,
  ]
  if (siteOrigin) {
    const address = siteOrigin + page.path
    headLines.push(`<link rel="canonical" href="${escapeHtml(address)}" />`)
    headLines.push(`<meta property="og:url" content="${escapeHtml(address)}" />`)
  }
  const body = `<div id="root"><main class="page-summary"><h1>${escapeHtml(heading)}</h1>`
    + `<p>${escapeHtml(page.summary)}</p></main></div>`
  return template
    .replace(/<title>[^<]*<\/title>/, headLines.join('\n    '))
    .replace('<div id="root"></div>', body)
}

let count = 0
for (const page of Object.values(pages)) {
  if (page.path === '/') {
    writeFileSync(join(distFolder, 'index.html'), pageHtml(page))
  } else {
    const file = join(distFolder, 'pages', `${page.path.slice(1)}.html`)
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, pageHtml(page))
  }
  count += 1
}
console.log(`page files: ${count} for ${siteName}${siteOrigin ? ` at ${siteOrigin}` : ' (no SITE_ORIGIN, no canonical links)'}`)
