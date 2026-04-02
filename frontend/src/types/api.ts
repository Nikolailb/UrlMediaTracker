export type PatternSource = 'AUTO' | 'MANUAL'
export type CheckStrategy = 'INCREMENTAL_PROBE'
export type PatternConfidence = 'HIGH' | 'MEDIUM' | 'LOW'

export interface ItemRead {
  id: string
  title: string | null
  original_url: string
  url_template: string | null
  chapter_regex: string | null
  pattern_source: PatternSource
  check_strategy: CheckStrategy
  current_chapter: string | null
  latest_chapter: string | null
  check_interval_min: number
  last_checked_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  user_id: string | null
  has_unread: boolean | null
}

export interface ItemCreate {
  url: string
  title?: string | null
  manual_regex?: string | null
  check_interval_min?: number
}

export interface ItemUpdate {
  title?: string | null
  manual_regex?: string | null
  check_interval_min?: number | null
  current_chapter?: string | null
  is_active?: boolean | null
}

export interface MarkReadRequest {
  chapter: string
}

export interface NextChapterResponse {
  item_id: string
  next_chapter: string | null
  next_url: string | null
  message: string
}

export interface PatternDetectionRequest {
  url: string
  manual_regex?: string | null
}

export interface PatternDetectionResult {
  url_template: string | null
  chapter_regex: string | null
  current_chapter: string | null
  confidence: PatternConfidence
  strategy_used: string
  pattern_source: PatternSource
}

export interface CheckResult {
  success: boolean
  previous_latest_chapter: string | null
  new_latest_chapter: string | null
  error_message: string | null
}

export interface CheckAllResult {
  checked: number
  results: Array<{
    item_id: string
    title: string | null
    success: boolean
    new_latest_chapter: string | null
  }>
}
