import { useState, type FormEvent } from 'react'
import { CheckError, checkStore } from './api'
import type { Report, Signal, Status } from './types'

// Human-readable names for the signal keys the API returns.
const SIGNAL_LABELS: Record<string, string> = {
  business_age: 'Business age',
  business_transparency: 'Business transparency',
  shipping_policy: 'Shipping & refund policy',
  independent_reviews: 'Independent reviews',
  photo_origin: 'Product photo origin',
}

// Fallback for signals added to the backend before the UI knows their label:
// "some_new_signal" -> "Some new signal".
function labelFor(key: string): string {
  const words = key.replaceAll('_', ' ')
  return SIGNAL_LABELS[key] ?? words.charAt(0).toUpperCase() + words.slice(1)
}

// Tailwind classes per status. The status word is always shown as text too,
// so the meaning never depends on colour alone (accessibility).
const STATUS_STYLES: Record<Status, string> = {
  good: 'bg-green-100 text-green-800',
  warning: 'bg-amber-100 text-amber-800',
  danger: 'bg-red-100 text-red-800',
  unknown: 'bg-slate-200 text-slate-700',
}

export default function App() {
  const [url, setUrl] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // stop the browser's default full-page form submit
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      setReport(await checkStore(url.trim()))
    } catch (err) {
      setError(err instanceof CheckError ? err.message : 'Unexpected error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900">Trust Checker</h1>
      <p className="mt-1 text-slate-600">
        Paste a store link to see evidence about the seller before you buy.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="store-url" className="sr-only">
          Store URL
        </label>
        <input
          id="store-url"
          type="text"
          inputMode="url"
          autoComplete="off"
          placeholder="https://example-store.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || url.trim() === ''}
          className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Checking…' : 'Check store'}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-red-800">
          {error}
        </p>
      )}

      {report && <ReportView report={report} />}
    </main>
  )
}

function ReportView({ report }: { report: Report }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-slate-900">Report</h2>
      <p className="text-sm break-all text-slate-500">{report.store_url}</p>

      {/* Honesty: the backend currently returns placeholder data for every URL. */}
      <p className="mt-3 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
        Sample data: real checks aren't built yet, so every store gets this same report.
      </p>

      <ul className="mt-4 flex flex-col gap-3">
        {Object.entries(report.signals).map(([key, signal]) => (
          <SignalRow key={key} name={labelFor(key)} signal={signal} />
        ))}
      </ul>
    </section>
  )
}

function SignalRow({ name, signal }: { name: string; signal: Signal }) {
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-900">{name}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${STATUS_STYLES[signal.status]}`}>
          {signal.status}
        </span>
      </div>
      <p className="mt-1 text-slate-700">{signal.detail}</p>
    </li>
  )
}
