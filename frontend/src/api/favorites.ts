import client from './client'
import type { Video } from '@/types/video'

/** Paginated favorites list response. */
export interface FavoriteListResponse {
  items: Video[]
  total: number
  page: number
  page_size: number
}

/** Get paginated favorite videos. */
export async function listFavorites(
  page = 1,
  pageSize = 20,
): Promise<FavoriteListResponse> {
  const response = await client.get<FavoriteListResponse>('/favorites', {
    params: { page, page_size: pageSize },
  })
  return response.data
}

/** Add a video to favorites. */
export async function addFavorite(videoId: number): Promise<void> {
  await client.post(`/favorites/${videoId}`)
}

/** Remove a video from favorites. */
export async function removeFavorite(videoId: number): Promise<void> {
  await client.delete(`/favorites/${videoId}`)
}

/** Check if a video is in favorites. */
export async function checkFavorite(videoId: number): Promise<boolean> {
  const response = await client.get<{ is_favorite: boolean }>(
    `/favorites/${videoId}/status`,
  )
  return response.data.is_favorite
}
