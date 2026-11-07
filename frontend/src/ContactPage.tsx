import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchContactSettings, sendContactMessage } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'

interface Recaptcha {
  ready: (callback: () => void) => void
  execute: (siteKey: string, options: { action: string }) => Promise<string>
}

declare global {
  interface Window {
    grecaptcha?: Recaptcha
  }
}

interface ContactPageProps {
  isHidden: boolean
}

// Loads Google's reCAPTCHA v3 script once (it works unseen: no box to tick) and says when it is ready.
let recaptchaScript: Promise<void> | null = null
function loadRecaptcha(siteKey: string): Promise<void> {
  if (!recaptchaScript) {
    recaptchaScript = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(siteKey)}`
      script.async = true
      script.onload = () => window.grecaptcha?.ready(resolve)
      script.onerror = () => {
        recaptchaScript = null
        reject(new Error('The check that you are not a robot could not be loaded.'))
      }
      document.head.appendChild(script)
    })
  }
  return recaptchaScript
}

// A form for writing to the owner of the site. The message is written in Quill and checked, cleaned and
// emailed by the server, using the email settings kept in Drupal.
function ContactPage({ isHidden }: ContactPageProps) {
  const [fullName, setFullName] = useState('')
  const [emailAddress, setEmailAddress] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [siteKey, setSiteKey] = useState<string | null>(null)
  const [setupMessage, setSetupMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSent, setIsSent] = useState(false)

  const editorReference = useRef<RichTextEditorHandle>(null)

  useEffect(() => {
    fetchContactSettings()
      .then((settings) => {
        if (settings.recaptcha_site_key) {
          setSiteKey(settings.recaptcha_site_key)
        } else {
          setSetupMessage('The contact form is not available right now.')
        }
      })
      .catch(() => setSetupMessage('The contact form is not available right now.'))
  }, [])

  // Google's script is loaded as soon as the form is, so a token is quick to get when Send is pressed.
  // Only once the page is opened, so a visitor who never uses the form never loads anything from Google.
  useEffect(() => {
    if (siteKey !== null && !isHidden) {
      loadRecaptcha(siteKey).catch((error: Error) => setErrorMessage(error.message))
    }
  }, [siteKey, isHidden])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const editor = editorReference.current
    if (!editor || siteKey === null || isSending) {
      return
    }
    setErrorMessage('')
    if (editor.isEmpty()) {
      setErrorMessage('Please enter a message.')
      return
    }
    setIsSending(true)
    try {
      // A new token for each message: Google rates this visit, with nothing for the visitor to do.
      await loadRecaptcha(siteKey)
      const token = await window.grecaptcha!.execute(siteKey, { action: 'contact' })
      await sendContactMessage({
        name: fullName,
        email: emailAddress,
        phone: phoneNumber,
        message: editor.getHtml(),
        recaptcha_token: token,
      })
      setIsSent(true)
      setFullName('')
      setEmailAddress('')
      setPhoneNumber('')
      editor.clear()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Your message could not be sent.')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="contact-page" hidden={isHidden}>
      <h1>Contact</h1>
      <p>Questions, corrections or comments are welcome. Fill in the form and your message will be sent by email.</p>

      {setupMessage && <p className="error">{setupMessage}</p>}

      {isSent && (
        <p className="contact-sent" role="status">
          Thank you. Your message has been sent.{' '}
          <button type="button" className="link-button" onClick={() => setIsSent(false)}>
            Send another message
          </button>
        </p>
      )}

      {siteKey !== null && !isSent && (
        <form className="contact-form" onSubmit={handleSubmit}>
          <label className="contact-field">
            Full Name*
            <input
              type="text"
              value={fullName}
              maxLength={100}
              required
              autoComplete="name"
              placeholder="Enter your full name (first and last)"
              onChange={(event) => setFullName(event.target.value)}
            />
          </label>
          <label className="contact-field">
            Email Address*
            <input
              type="email"
              value={emailAddress}
              maxLength={254}
              required
              autoComplete="email"
              placeholder="Enter your email address"
              onChange={(event) => setEmailAddress(event.target.value)}
            />
          </label>
          <label className="contact-field">
            Phone Number (optional)
            <input
              type="tel"
              value={phoneNumber}
              maxLength={40}
              autoComplete="tel"
              placeholder="Enter your phone number"
              onChange={(event) => setPhoneNumber(event.target.value)}
            />
          </label>

          <div className="contact-field">
            <span id="contact-message-label">Message*</span>
            <RichTextEditor ref={editorReference} placeholder="Write your message" labelledBy="contact-message-label" />
          </div>

          <p className="contact-required">* - Required Fields</p>

          <p className="contact-recaptcha-note">
            This form is protected by reCAPTCHA, and the Google{' '}
            <a href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">
              Privacy Policy
            </a>{' '}
            and{' '}
            <a href="https://policies.google.com/terms" target="_blank" rel="noreferrer">
              Terms of Service
            </a>{' '}
            apply.
          </p>

          {errorMessage && (
            <p className="error" role="alert">
              {errorMessage}
            </p>
          )}

          <button type="submit" className="primary-button" disabled={isSending}>
            {isSending ? 'Sending…' : 'Send Message'}
          </button>
        </form>
      )}
    </div>
  )
}

export default ContactPage
