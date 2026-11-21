import { canSendViaSms, deliveryChoice } from './deliveryChoice'

interface TextMessageChoicesProps {
  // The phone number typed above.
  phone: string
  phoneIsCell: boolean
  sendViaEmail: boolean
  sendViaSms: boolean
  // Send Multimedia Messages: the verse a day and the devotionals as a picture (message_cards.py).
  sendMultimedia: boolean
  onPhoneIsCellChange: (value: boolean) => void
  onSendViaEmailChange: (value: boolean) => void
  onSendViaSmsChange: (value: boolean) => void
  onSendMultimediaChange: (value: boolean) => void
  // False for an account with no email address (it logs in with its phone): no "Send via Email", the number is a
  // cell number, and texts are optional.
  hasEmail?: boolean
}

// Under the phone number (the sign-up form and the My account page): "This is a cell (mobile) number" once a
// number is typed (2026-11-15), then how the member's messages reach them (2026-11-16, the owner's request):
// "Send via Email" and "Send via SMS", one or both. SMS is disabled until there is a cell number; ticking it is
// the consent to texts, so the carrier warning and STOP/HELP sit under it. The box that is the only one ticked
// cannot be unticked. The server checks again (accounts.py, sms.py): texts only to a US or Canadian cell number.
// Then "Send Multimedia Messages" (2026-11-16): the verse a day and the devotionals as a picture, by email and
// by text alike.
function TextMessageChoices({
  phone,
  phoneIsCell,
  sendViaEmail,
  sendViaSms,
  sendMultimedia,
  onPhoneIsCellChange,
  onSendViaEmailChange,
  onSendViaSmsChange,
  onSendMultimediaChange,
  hasEmail = true,
}: TextMessageChoicesProps) {
  const hasPhone = phone.trim() !== ''
  const smsAllowed = hasEmail ? canSendViaSms(phone, phoneIsCell) : hasPhone
  const shown = deliveryChoice(phone, phoneIsCell, sendViaEmail, sendViaSms, hasEmail)
  if (!hasEmail) {
    return (
      <div className="prayer-options text-message-choices">
        <fieldset className="prayer-options delivery-choices">
          <legend>How should we send you messages?</legend>
          <p className="delivery-choices-note">
            With no email address, nothing comes by email. The verse a day and your groups&rsquo; messages can come as
            texts to your phone if you tick below; everything else on the site works either way.
          </p>
          <label className="inline-label">
            <input
              type="checkbox"
              checked={shown.sendViaSms}
              disabled={!smsAllowed}
              onChange={(event) => onSendViaSmsChange(event.target.checked)}
            />
            Send via SMS
            <small>
              A short text message with a link, to the number above. <strong>Your mobile carrier may charge you for
              text messages</strong> (message and data rates may apply). Reply STOP to any text to stop them, or HELP
              for help. US and Canadian numbers only. See the{' '}
              <a href="/sms-terms" target="_blank" rel="noopener">
                text message terms
              </a>
              .
            </small>
          </label>
          <label className="inline-label">
            <input type="checkbox" checked={sendMultimedia} onChange={(event) => onSendMultimediaChange(event.target.checked)} />
            Send Multimedia Messages
            <small>The verse a day comes as a picture text (MMS), which your carrier may charge more for.</small>
          </label>
        </fieldset>
      </div>
    )
  }
  return (
    <div className="prayer-options text-message-choices">
      {hasPhone && (
        <label className="inline-label">
          <input type="checkbox" checked={phoneIsCell} onChange={(event) => onPhoneIsCellChange(event.target.checked)} />
          This is a cell (mobile) number
        </label>
      )}
      <fieldset className="prayer-options delivery-choices">
        <legend>How should we send you messages?</legend>
        <p className="delivery-choices-note">
          The devotionals, the verse a day, the prayer list and replies to your posts come the way you choose here.
          Emails about your account (confirming your address, resetting your password) always come by email.
        </p>
        <label className="inline-label">
          <input
            type="checkbox"
            checked={shown.sendViaEmail}
            disabled={!shown.sendViaSms}
            onChange={(event) => onSendViaEmailChange(event.target.checked)}
          />
          Send via Email
        </label>
        <label className="inline-label">
          <input
            type="checkbox"
            checked={shown.sendViaSms}
            disabled={!smsAllowed || !shown.sendViaEmail}
            onChange={(event) => {
              onSendViaSmsChange(event.target.checked)
              if (!event.target.checked) {
                onSendViaEmailChange(true)
              }
            }}
          />
          Send via SMS
          {smsAllowed ? (
            <small>
              A short text message with a link, to the number above. <strong>Your mobile carrier may charge you for
              text messages</strong> (message and data rates may apply). Reply STOP to any text to stop them, or HELP
              for help. US and Canadian numbers only. See the{' '}
              <a href="/sms-terms" target="_blank" rel="noopener">
                text message terms
              </a>
              .
            </small>
          ) : (
            <small>
              {hasPhone
                ? 'Tick “This is a cell (mobile) number” to choose SMS.'
                : 'Add a cell (mobile) phone number above to choose SMS.'}
            </small>
          )}
        </label>
        {smsAllowed && shown.sendViaEmail !== shown.sendViaSms && (
          <p className="delivery-choices-note">At least one must be ticked: to switch, tick the other one first.</p>
        )}
        <label className="inline-label">
          <input type="checkbox" checked={sendMultimedia} onChange={(event) => onSendMultimediaChange(event.target.checked)} />
          Send Multimedia Messages
          <small>
            The verse a day and the daily devotional come as a picture: the words written over a photograph, in the
            email and with the text message (a picture text, MMS, which your carrier may charge more for). The
            prayer list and replies stay as words.
          </small>
        </label>
      </fieldset>
    </div>
  )
}

export default TextMessageChoices
