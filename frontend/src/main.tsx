import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { domainTitle } from './domainTitle'

// A domain with its own name shows it in the tab at once, not only after the site settings arrive.
const ownTitle = domainTitle()
if (ownTitle !== null) {
  document.title = ownTitle
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
