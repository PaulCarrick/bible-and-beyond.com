// API.Bible asks every site that shows its licensed text to report each view (FUMS).
// The device id is random, stays in this browser, and does not identify the person.
const deviceIdKey = 'bibleAndBeyondDeviceId'

function getDeviceId() {
  try {
    let deviceId = localStorage.getItem(deviceIdKey)
    if (!deviceId) {
      deviceId = crypto.randomUUID()
      localStorage.setItem(deviceIdKey, deviceId)
    }
    return deviceId
  } catch {
    return 'unknown'
  }
}

export function reportView(token: string) {
  const query = new URLSearchParams({ t: token, dId: getDeviceId() })
  // An image request is a simple way to send the report without needing a response.
  new Image().src = `https://fums.api.bible/f3?${query}`
}
