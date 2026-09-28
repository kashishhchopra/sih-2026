// Offline SOS queue.
//
// The one thing this app cannot afford to just fail silently on a bad
// connection is the SOS button -- a tourist in an emergency with patchy
// signal needs the tap to be remembered and retried, not lost. This is
// deliberately a small, hand-rolled localStorage queue rather than the
// service worker's Background Sync API: Background Sync retries silently
// with no hook for "tell the user it's queued" or "tell them it went
// through", and browser support for it is still inconsistent (notably
// absent in Safari/iOS) -- exactly the platform an emergency feature cannot
// gamble on.
const STORAGE_KEY = 'stsOfflineSosQueue'

function readQueue() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeQueue(queue) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue))
  } catch {
    // Storage full/unavailable: the queue just won't persist across a
    // reload, which is a reasonable degradation, not a crash.
  }
}

export function enqueueSOS(payload) {
  const entry = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, payload, queuedAt: Date.now() }
  writeQueue([...readQueue(), entry])
  return entry.id
}

export function getQueue() {
  return readQueue()
}

export function queueLength() {
  return readQueue().length
}

function removeFromQueue(id) {
  writeQueue(readQueue().filter((e) => e.id !== id))
}

// Sends queued entries oldest-first via `sendFn(payload) -> Promise`.
// Stops at the first failure (still offline, or a real server error) rather
// than reordering or dropping entries -- the ones behind it get another
// chance on the next flush. Returns how many were successfully sent.
export async function flushQueue(sendFn) {
  const queue = readQueue()
  let sent = 0
  for (const entry of queue) {
    try {
      await sendFn(entry.payload)
      removeFromQueue(entry.id)
      sent += 1
    } catch {
      break
    }
  }
  return sent
}
