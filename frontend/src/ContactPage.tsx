import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'
import { fetchContactSettings, sendContactMessage } from './api'

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

  const toolbarReference = useRef<HTMLDivElement>(null)
  const editorReference = useRef<HTMLDivElement>(null)
  const quillReference = useRef<Quill | null>(null)

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

  // The editor is made once the form is on the page.
  useEffect(() => {
    if (siteKey === null || quillReference.current || !editorReference.current || !toolbarReference.current) {
      return
    }
    quillReference.current = new Quill(editorReference.current, {
      theme: 'snow',
      modules: { toolbar: toolbarReference.current, history: { delay: 1000, maxStack: 100 } },
      placeholder: 'Write your message',
    })
  }, [siteKey])

  // Google's script is loaded as soon as the form is, so a token is quick to get when Send is pressed.
  useEffect(() => {
    if (siteKey !== null) {
      loadRecaptcha(siteKey).catch((error: Error) => setErrorMessage(error.message))
    }
  }, [siteKey])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const quill = quillReference.current
    if (!quill || siteKey === null || isSending) {
      return
    }
    setErrorMessage('')
    if (quill.getText().trim() === '') {
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
        message: quill.getSemanticHTML(),
        recaptcha_token: token,
      })
      setIsSent(true)
      setFullName('')
      setEmailAddress('')
      setPhoneNumber('')
      quill.setText('')
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
            <div className="contact-editor" role="group" aria-labelledby="contact-message-label">
              <div ref={toolbarReference} className="contact-toolbar">
                <span className="ql-formats">
                  <button type="button" className="ql-bold" aria-label="Bold" />
                  <button type="button" className="ql-italic" aria-label="Italic" />
                  <button type="button" className="ql-strike" aria-label="Strikethrough" />
                  <button type="button" className="ql-link" aria-label="Link" />
                </span>
                <span className="ql-formats">
                  <button type="button" className="ql-header" value="2" aria-label="Heading" />
                  <button type="button" className="ql-blockquote" aria-label="Quote" />
                  <button type="button" className="ql-code-block" aria-label="Code" />
                  <button type="button" className="ql-list" value="bullet" aria-label="Bulleted list" />
                  <button type="button" className="ql-list" value="ordered" aria-label="Numbered list" />
                </span>
                <span className="ql-formats">
                  <button type="button" onClick={() => quillReference.current?.history.undo()} aria-label="Undo">
                    ↶
                  </button>
                  <button type="button" onClick={() => quillReference.current?.history.redo()} aria-label="Redo">
                    ↷
                  </button>
                </span>
              </div>
              <div ref={editorReference} className="contact-text" />
            </div>
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
