import client from './client'
import type { Video, VideoListResponse, VideoQueryParams, VideoUpdate } from '@/types/video'

/** Get paginated video list with optional filtering. */
export function listVideos(params: VideoQueryParams = {}): Promise<VideoListResponse> {
  return client
    .get<VideoListResponse>('/videos', { params })
    .then((r) => r.data)
}

/** Get a single video by ID. */
export function getVideo(id: number): Promise<Video> {
  return client.get<Video>(`/videos/${id}`).then((r) => r.data)
}

/** Update video information. */
export function updateVideo(id: number, data: VideoUpdate): Promise<Video> {
  return client.put<Video>(`/videos/${id}`, data).then((r) => r.data)
}

/** Delete a video by ID. */
export function deleteVideo(id: number): Promise<void> {
  return client.delete(`/videos/${id}`).then(() => undefined)
}

/** Get newly discovered videos. */
export function getNewVideos(sourceId?: number): Promise<Video[]> {
  return client
    .get<Video[]>('/videos/new', { params: { source_id: sourceId } })
    .then((r) => r.data)
}

/** Mark a new video as viewed. */
export function markVideoViewed(id: number): Promise<void> {
  return client.post(`/videos/new/${id}/viewed`).then(() => undefined)
}

/** Record that a video started playing. */
export function recordPlay(id: number): Promise<void> {
  return client.post(`/videos/${id}/play`).then(() => undefined)
}

/** Report playback progress. */
export function updateProgress(id: number, progress: number): Promise<void> {
  return client.post(`/videos/${id}/progress`, { progress }).then(() => undefined)
}
