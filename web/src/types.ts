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

export interface ScanResponse {
  video: VideoInfo | null
  extraction: Extraction
}
