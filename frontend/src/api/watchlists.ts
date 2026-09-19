import client from './client'
import type { Video } from '@/types/video'

/** A hand-picked queue of titles, such as 今晚看这些. */
export interface Watchlist {
  id: number
  name: string
  description: string | null
  created_at: string
  /** The queue, in the order the titles were added. */
  items: Video[]
}

/** List every watchlist, or only those holding `videoId`. */
export async function listWatchlists(videoId?: number): Promise<Watchlist[]> {
  const response = await client.get<Watchlist[]>('/watchlists', {
    params: videoId ? { video_id: videoId } : undefined,
  })
  return response.data
}

/** Create an empty watchlist. */
export async function createWatchlist(
  name: string,
  description?: string | null,
): Promise<Watchlist> {
  const response = await client.post<Watchlist>('/watchlists', {
    name,
    description: description || null,
  })
  return response.data
}

/** Rename a watchlist or edit its description. */
export async function updateWatchlist(
  id: number,
  payload: { name?: string; description?: string | null },
): Promise<Watchlist> {
  const response = await client.put<Watchlist>(`/watchlists/${id}`, payload)
  return response.data
}

/** Delete a watchlist. The titles inside stay in the library. */
export async function deleteWatchlist(id: number): Promise<void> {
  await client.delete(`/watchlists/${id}`)
}

/** Put a title at the end of the queue. */
export async function addVideoToWatchlist(
  id: number,
  videoId: number,
): Promise<Watchlist> {
  const response = await client.post<Watchlist>(`/watchlists/${id}/videos`, {
    video_id: videoId,
  })
  return response.data
}

/** Take a title out of the queue without touching the library. */
export async function removeVideoFromWatchlist(
  id: number,
  videoId: number,
): Promise<Watchlist> {
  const response = await client.delete<Watchlist>(
    `/watchlists/${id}/videos/${videoId}`,
  )
  return response.data
}
