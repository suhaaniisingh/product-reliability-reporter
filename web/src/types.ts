// TypeScript mirror of the API contract in backend/app/schemas.py.
// If the backend's report shape changes, update these types to match;
// the compiler will then point at every place in the UI that needs fixing.

export type Status = 'good' | 'warning' | 'danger' | 'unknown'

export interface Signal {
  status: Status
  detail: string
}

export interface Report {
  store_url: string
  signals: Record<string, Signal>
}
