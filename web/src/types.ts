// TypeScript mirror of the API contract in backend/app/schemas.py.
// If the backend's shapes change, update these types to match;
// the compiler will then point at every place in the UI that needs fixing.

export type Platform = 'tiktok' | 'instagram' | 'unknown'
export type StoreUrlSource = 'in_caption' | 'user_provided' | 'guessed_from_brand' | 'none'
export type Confidence = 'high' | 'medium' | 'low'

export interface ScanRequest {
  caption?: string
  store_url?: string
  video_url?: string
}

export interface VideoInfo {
  platform: Platform
  video_id: string | null
  creator_handle: string | null
}

export interface Extraction {
  product: string | null
  brand: string | null
  store_url: string | null
  store_url_source: StoreUrlSource
  mentions_link_in_bio: boolean
  discount_code: string | null
  confidence: Confidence
  notes: string
}

export type SignalStatus = 'ok' | 'failed' | 'timeout'

export interface SignalResult {
  name: string
  label: string
  status: SignalStatus
  value: Record<string, unknown> | null
  explanation: string
  source: string | null // attribution required by some data sources (e.g. Google)
  duration_ms: number
}

export interface Reason {
  points: number
  text: string
  signal: string
  cap: number | null // set when this reason caps the score instead of adding points
}

export interface TrustReport {
  score: number // 0-100
  label: string // "Higher trust" | "Mixed signals" | "Lower trust"
  confidence: Confidence
  reasons: Reason[]
  notes: string[]
  signals: SignalResult[]
}

export interface ScanResponse {
  video: VideoInfo | null
  extraction: Extraction
  trust: TrustReport | null // null when no store was identified
}
