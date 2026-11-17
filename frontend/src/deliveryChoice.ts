// Whether "Send via SMS" can be ticked: it needs a phone number marked as a cell number.
export function canSendViaSms(phone: string, phoneIsCell: boolean): boolean {
  return phone.trim() !== '' && phoneIsCell
}

// What is saved for the two boxes: SMS only with a cell number, and email whenever SMS is off (the server does
// the same), so a member can always be reached. An account with no email address (it logs in with its phone,
// 2026-11-17) is never sent email: its number is a cell number, and texts are its only choice (or nothing).
export function deliveryChoice(phone: string, phoneIsCell: boolean, sendViaEmail: boolean, sendViaSms: boolean, hasEmail = true) {
  if (!hasEmail) {
    return { sendViaEmail: false, sendViaSms: phone.trim() !== '' && sendViaSms }
  }
  const viaSms = canSendViaSms(phone, phoneIsCell) && sendViaSms
  return { sendViaEmail: sendViaEmail || !viaSms, sendViaSms: viaSms }
}
