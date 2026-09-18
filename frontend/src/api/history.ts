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

/** Delete a history record. */
export async function deleteHistory(id: number): Promise<void> {
  await client.delete(`/history/${id}`)
}
