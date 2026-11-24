import { useState, type FormEvent } from 'react'
import { ScanError, scan } from './api'
import type { Confidence, Extraction, Reason, ScanRequest, ScanResponse, SignalResult, StoreUrlSource, TrustReport, VideoInfo } from './types'

// How each store source is shown. Text always accompanies colour (accessibility).
const SOURCE_BADGES: Record<StoreUrlSource, { label: string; style: string }> = {
  in_caption: { label: 'From the caption', style: 'bg-green-100 text-green-800' },
  user_provided: { label: 'Your link', style: 'bg-blue-100 text-blue-800' },
  guessed_from_brand: { label: 'Guessed from the brand', style: 'bg-amber-100 text-amber-800' },
  none: { label: 'Not found', style: 'bg-slate-200 text-slate-700' },
}

const CONFIDENCE_LABELS: Record<Confidence, string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence',
}

const PLATFORM_LABELS = { tiktok: 'TikTok', instagram: 'Instagram', unknown: 'Unrecognized site' } as const

const INPUT_STYLE =
  'w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none'

export default function App() {
  const [caption, setCaption] = useState('')
  const [storeUrl, setStoreUrl] = useState('')
  const [videoUrl, setVideoUrl] = useState('')
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const canSubmit = caption.trim() !== '' || storeUrl.trim() !== ''

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // stop the browser's default full-page form submit
    // Only send fields the user filled in.
    const request: ScanRequest = {}
    if (caption.trim()) request.caption = caption.trim()
    if (storeUrl.trim()) request.store_url = storeUrl.trim()
    if (videoUrl.trim()) request.video_url = videoUrl.trim()

    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await scan(request))
    } catch (err) {
      setError(err instanceof ScanError ? err.message : 'Unexpected error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900">Reliability Reporter</h1>
      <p className="mt-1 text-slate-600">
        Paste a product video's caption, the store link, or both, to see which store is selling it and how
        trustworthy it looks, with the evidence behind the score.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div>
          <label htmlFor="caption" className="block text-sm font-medium text-slate-800">
            Video caption
          </label>
          <textarea
            id="caption"
            rows={4}
            maxLength={5000}
            placeholder="Obsessed w this serum 😍 code GLOW20 at glowlab.co"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            className={`mt-1 ${INPUT_STYLE}`}
          />
        </div>

        <div>
          <label htmlFor="store-url" className="block text-sm font-medium text-slate-800">
            Store link <span className="font-normal text-slate-500">(if the caption says "link in bio", paste it here)</span>
          </label>
          <input
            id="store-url"
            type="text"
            inputMode="url"
            autoComplete="off"
            placeholder="glowlab.co"
            value={storeUrl}
            onChange={(e) => setStoreUrl(e.target.value)}
            className={`mt-1 ${INPUT_STYLE}`}
          />
        </div>

        <div>
          <label htmlFor="video-url" className="block text-sm font-medium text-slate-800">
            Video link <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input
            id="video-url"
            type="url"
            autoComplete="off"
            placeholder="https://www.tiktok.com/@creator/video/…"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            className={`mt-1 ${INPUT_STYLE}`}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !canSubmit}
          className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Scanning…' : 'Scan'}
        </button>
        <p className="text-xs text-slate-500">
          To check a store, its link is looked up with Google Safe Browsing and its public pages are visited.
        </p>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-red-800">
          {error}
        </p>
      )}

      {result && <ResultView extraction={result.extraction} video={result.video} trust={result.trust} />}
    </main>
  )
}

function ResultView({
  extraction,
  video,
  trust,
}: {
  extraction: Extraction
  video: VideoInfo | null
  trust: TrustReport | null
}) {
  const badge = SOURCE_BADGES[extraction.store_url_source]
  return (
    <section className="mt-8 flex flex-col gap-3" aria-live="polite">
      <h2 className="text-lg font-semibold text-slate-900">Result</h2>

      <div className="rounded-lg border border-slate-200 p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="font-medium text-slate-900">Store</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badge.style}`}>{badge.label}</span>
        </div>
        {/* Plain text on purpose: we haven't checked this store yet, so we don't link to it. */}
        <p className="mt-1 break-all text-slate-800">{extraction.store_url ?? 'No store found'}</p>
        <p className="mt-1 text-sm text-slate-500">{CONFIDENCE_LABELS[extraction.confidence]}</p>
      </div>

      {trust && <TrustView trust={trust} />}

      {extraction.mentions_link_in_bio && extraction.store_url_source !== 'user_provided' && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          The caption says the link is in the creator's bio. Open their profile, copy the store link, and paste it
          above to check the exact store.
        </p>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border border-slate-200 p-3 text-sm">
        <Field label="Product" value={extraction.product} />
        <Field label="Brand" value={extraction.brand} />
        <Field label="Discount code" value={extraction.discount_code} />
        {video && (
          <Field
            label="Video"
            value={[PLATFORM_LABELS[video.platform], video.creator_handle && `@${video.creator_handle}`]
              .filter(Boolean)
              .join(' · ')}
          />
        )}
      </dl>

      {extraction.notes && <p className="text-sm text-slate-600">{extraction.notes}</p>}
    </section>
  )
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <dt className="font-medium text-slate-700">{label}</dt>
      <dd className="text-slate-900">{value || <span className="text-slate-400">—</span>}</dd>
    </>
  )
}

// Colour follows the label; the label text is always shown too (never colour alone).
const LABEL_STYLES: Record<string, string> = {
  'Higher trust': 'bg-green-100 text-green-800',
  'Mixed signals': 'bg-amber-100 text-amber-800',
  'Lower trust': 'bg-red-100 text-red-800',
}

function TrustView({ trust }: { trust: TrustReport }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-900">Trust score</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${LABEL_STYLES[trust.label] ?? 'bg-slate-200 text-slate-700'}`}>
          {trust.label}
        </span>
      </div>
      <p className="mt-1 text-3xl font-bold text-slate-900">
        {trust.score}
        <span className="text-base font-normal text-slate-500"> / 100</span>
      </p>
      <p className="text-sm text-slate-500">{CONFIDENCE_LABELS[trust.confidence]} (how complete the evidence is)</p>

      {trust.notes.map((note) => (
        <p key={note} className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {note}
        </p>
      ))}

      <h3 className="mt-3 text-sm font-semibold text-slate-800">Why (every store starts at 50)</h3>
      <ul className="mt-1 flex flex-col gap-1">
        {trust.reasons.map((reason) => (
          <ReasonRow key={`${reason.signal}:${reason.text}`} reason={reason} />
        ))}
      </ul>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-slate-700">Details of each check</summary>
        <ul className="mt-2 flex flex-col gap-2">
          {trust.signals.map((signal) => (
            <SignalDetail key={signal.name} signal={signal} />
          ))}
        </ul>
      </details>

      <p className="mt-3 text-xs text-slate-500">
        This score summarises public evidence about the store. It isn't a guarantee either way.
      </p>
    </div>
  )
}

function ReasonRow({ reason }: { reason: Reason }) {
  const badge =
    reason.cap !== null
      ? { text: `capped at ${reason.cap}`, style: 'bg-red-100 text-red-800' }
      : reason.points > 0
        ? { text: `+${reason.points}`, style: 'bg-green-100 text-green-800' }
        : reason.points < 0
          ? { text: `${reason.points}`, style: 'bg-red-100 text-red-800' }
          : { text: '0', style: 'bg-slate-100 text-slate-600' }
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className={`w-24 shrink-0 rounded px-1.5 py-0.5 text-center text-xs font-semibold ${badge.style}`}>{badge.text}</span>
      <span className="text-slate-800">{reason.text}</span>
    </li>
  )
}

// Some sources require attribution with a link ("Advisory provided by Google: <url>").
function SourceLine({ source }: { source: string }) {
  const match = source.match(/^(.*?):\s*(https?:\/\/\S+)$/)
  if (!match) return <p className="text-xs text-slate-500">{source}</p>
  return (
    <p className="text-xs text-slate-500">
      <a href={match[2]} target="_blank" rel="noopener noreferrer" className="underline">
        {match[1]}
      </a>
    </p>
  )
}

function SignalDetail({ signal }: { signal: SignalResult }) {
  return (
    <li className="rounded border border-slate-100 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-slate-800">{signal.label}</span>
        <span className="text-xs text-slate-500">
          {signal.status === 'ok' ? 'checked' : signal.status === 'timeout' ? 'timed out' : 'not checked'}
        </span>
      </div>
      <p className="text-slate-700">{signal.explanation}</p>
      {signal.source && <SourceLine source={signal.source} />}
    </li>
  )
}
