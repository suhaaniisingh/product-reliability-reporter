import type { ScanRequest, ScanResponse } from './types'

// Thrown for problems we can explain to the user in plain English.
export class ScanError extends Error {}

// FastAPI's 422 body: { detail: [{ msg: "Value error, ..." }, ...] }.
// Other errors we raise ourselves: { detail: "..." }.
function messageFrom(body: unknown): string | null {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return detail[0].msg.replace(/^Value error, /, '')
  }
  return null
}

// Calls POST /api/scan. The path is relative ("/api/..."), so it goes to
// whatever origin served the page: the Vite dev proxy in development,
// FastAPI itself in production. No API address is hardcoded.
export async function scan(request: ScanRequest): Promise<ScanResponse> {
  let response: Response
  try {
    response = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  } catch {
    // fetch only throws when no response arrived at all (server down, offline).
    throw new ScanError("Couldn't reach the server. Is the backend running?")
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = messageFrom(body)
    if (response.status === 422) {
      throw new ScanError(detail ?? 'Please check what you entered and try again.')
    }
    // 502 (extraction service failed) and 503 (not configured) carry a readable detail.
    throw new ScanError(detail ?? `Something went wrong on our side (HTTP ${response.status}). Please try again.`)
  }
  return (await response.json()) as ScanResponse
}
