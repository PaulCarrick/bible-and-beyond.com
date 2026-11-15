// US phone numbers are shown as +1 (555) 123-4567 (the owner's request, 2026-11-15; the server keeps them that way
// too, sms.format_phone). A number starting with + and another country code is left as typed.

function usDigits(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed.startsWith('+') && !trimmed.startsWith('+1')) {
    return null
  }
  let digits = value.replace(/\D/g, '')
  // The country code 1, typed or already in the box.
  if (trimmed.startsWith('+1') || (digits.length === 11 && digits.startsWith('1'))) {
    digits = digits.slice(1)
  }
  return digits.slice(0, 10)
}

// The number as far as it has been typed: "+1 (555", "+1 (555) 123", "+1 (555) 123-4567".
export function formatUsPhone(value: string): string {
  const digits = usDigits(value)
  if (digits === null || value.trim() === '') {
    return value
  }
  if (digits.length === 0) {
    return ''
  }
  let formatted = `+1 (${digits.slice(0, 3)}`
  if (digits.length >= 3) {
    formatted += ')'
  }
  if (digits.length > 3) {
    formatted += ` ${digits.slice(3, 6)}`
  }
  if (digits.length > 6) {
    formatted += `-${digits.slice(6)}`
  }
  return formatted
}

// For a phone box's onChange: formats as the number is typed, but leaves a deletion alone (so Backspace can remove
// a bracket or a dash), and formats fully once ten digits are there.
export function nextPhoneValue(previous: string, typed: string): string {
  const digits = usDigits(typed)
  if (digits !== null && digits.length === 10) {
    return formatUsPhone(typed)
  }
  return typed.length > previous.length ? formatUsPhone(typed) : typed
}
