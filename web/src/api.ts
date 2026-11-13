import type { Report } from './types'

// Thrown for problems we can explain to the user in plain English.
export class CheckError extends Error {}

// Calls POST /api/check. The path is relative ("/api/..."), so it goes to
// whatever origin served the page: the Vite dev proxy in development,
// FastAPI itself in production. No API address is hardcoded.
export async function checkStore(url: string): Promise<Report> {
  let response: Response
  try {
    response = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
  } catch {
    // fetch only throws when no response arrived at all (server down, offline).
    throw new CheckError("Couldn't reach the server. Is the backend running?")
  }

  if (response.status === 422) {
    throw new CheckError('That doesn\'t look like a full link. Paste the whole URL, starting with https://')
  }
  if (!response.ok) {
    throw new CheckError(`Something went wrong on our side (HTTP ${response.status}). Please try again.`)
  }
  return (await response.json()) as Report
}
