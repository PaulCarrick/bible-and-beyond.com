import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchContactSettings, sendContactMessage } from './api'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'

interface Recaptcha {
  ready: (callback: () => void) => void
  // Draws the reCAPTCHA badge inside an element (explicit rendering) and returns the widget's id.
  render: (container: HTMLElement, parameters: { sitekey: string; badge: 'inline'; size: 'invisible' }) => number
  execute: (widgetId: number, options: { action: string }) => Promise<string>
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
// "render=explicit" means Google draws no badge of its own (its usual badge floats in the corner of every
// page from then on); the form draws it inline instead, so it shows only with the form.
let recaptchaScript: Promise<void> | null = null
function loadRecaptcha(): Promise<void> {
  if (!recaptchaScript) {
    recaptchaScript = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://www.google.com/recaptcha/api.js?render=explicit'
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
  // Where the reCAPTCHA badge is drawn, inside the form, and the id Google gave the badge drawn there.
  const badgeReference = useRef<HTMLDivElement>(null)
  const widgetId = useRef<number | null>(null)

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

  // Google's script is loaded, and the badge drawn in the form, as soon as the form is shown, so a token is
  // quick to get when Send is pressed. Only once the page is opened, so a visitor who never uses the form
  // never loads anything from Google. The badge is part of the form: it goes when the message has been
  // sent (the form is replaced by the thank-you note) and when another page is opened (this page is
  // hidden), and is drawn again for "Send another message".
  useEffect(() => {
    if (siteKey === null || isHidden || isSent) {
      return
    }
    const container = badgeReference.current
    if (!container || widgetId.current !== null) {
      return
    }
    let isCurrent = true
    loadRecaptcha()
      .then(() => {
        if (isCurrent && widgetId.current === null && window.grecaptcha) {
          widgetId.current = window.grecaptcha.render(container, { sitekey: siteKey, badge: 'inline', size: 'invisible' })
        }
      })
      .catch((error: Error) => setErrorMessage(error.message))
    return () => {
      isCurrent = false
    }
  }, [siteKey, isHidden, isSent])

  // The form (and the badge in it) is removed once a message is sent; a new one is drawn with the next form.
  useEffect(() => {
    if (isSent) {
      widgetId.current = null
    }
  }, [isSent])

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
      await loadRecaptcha()
      if (widgetId.current === null) {
        throw new Error('The check that you are not a robot is still loading. Please try again in a moment.')
      }
      const token = await window.grecaptcha!.execute(widgetId.current, { action: 'contact' })
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
          <div ref={badgeReference} className="contact-recaptcha-badge" />

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
