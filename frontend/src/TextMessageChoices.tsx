interface TextMessageChoicesProps {
  // The phone number typed above; the choices show only once there is one.
  phone: string
  phoneIsCell: boolean
  smsOptIn: boolean
  onPhoneIsCellChange: (value: boolean) => void
  onSmsOptInChange: (value: boolean) => void
}

// The two checkboxes under a phone number (the sign-up form and the My account page; the owner's request,
// 2026-11-15): "This is a cell number", then, once ticked, "Send me text messages" with the warning that texts can
// cost. The server checks again (sms.py): texts only to a US or Canadian cell number.
function TextMessageChoices({ phone, phoneIsCell, smsOptIn, onPhoneIsCellChange, onSmsOptInChange }: TextMessageChoicesProps) {
  if (phone.trim() === '') {
    return null
  }
  return (
    <div className="prayer-options text-message-choices">
      <label className="inline-label">
        <input
          type="checkbox"
          checked={phoneIsCell}
          onChange={(event) => {
            onPhoneIsCellChange(event.target.checked)
            if (!event.target.checked) {
              onSmsOptInChange(false)
            }
          }}
        />
        This is a cell (mobile) number
      </label>
      {phoneIsCell && (
        <label className="inline-label">
          <input type="checkbox" checked={smsOptIn} onChange={(event) => onSmsOptInChange(event.target.checked)} />
          Send me text (SMS) messages
          <small>
            The devotionals, verse a day, prayer list and reply notices you get by email will also be texted to this number, as a short
            message with a link. <strong>Your mobile carrier may charge you for text messages</strong> (message and data
            rates may apply). Reply STOP to any text to stop them, or HELP for help. US and Canadian numbers only.
          </small>
        </label>
      )}
    </div>
  )
}

export default TextMessageChoices
