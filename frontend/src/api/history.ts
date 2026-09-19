import client from './client'
import type { Video } from '@/types/video'

/** A history record from the backend. */
export interface HistoryItem {
  id: number
  video_id: number
  played_at: string
  progress: number
  completed: boolean
  video_title: string | null
}

/** Paginated history list response. */
export interface HistoryListResponse {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

/** One bar of the daily chart, always present even on a day nothing was watched. */
export interface WatchDay {
  date: string
  seconds: number
  videos: number
}

/** How much of the window a single tag accounts for. */
export interface WatchTag {
  name: string
  color: string
  seconds: number
}

/** Everything the stats page shows, from one aggregate query. */
export interface WatchStats {
  days: number
  window_seconds: number
  month_seconds: number
  videos_watched: number
  active_days: number
  longest_streak_days: number
  daily: WatchDay[]
  tags: WatchTag[]
}

/** Get paginated playback history. */
export async function listHistory(
  page = 1,
  pageSize = 20,
): Promise<HistoryListResponse> {
  const response = await client.get<HistoryListResponse>('/history', {
    params: { page, page_size: pageSize },
  })
  return response.data
}

/** Get videos to continue watching. */
export async function getContinueList(): Promise<Video[]> {
  const response = await client.get<Video[]>('/history/continue')
  return response.data
}

/** Get watch totals, the daily chart and the tag split over `days` days. */
export async function getWatchStats(days = 30): Promise<WatchStats> {
  const response = await client.get<WatchStats>('/history/stats', {
    params: { days },
  })
  return response.data
}

/** Delete a history record. */
export async function deleteHistory(id: number): Promise<void> {
  await client.delete(`/history/${id}`)
}
