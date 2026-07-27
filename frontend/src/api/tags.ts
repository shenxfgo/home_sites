import client from './client'
import type { Tag, TagCreate, TagUpdate } from '@/types/video'

/** List all tags. */
export function listTags(): Promise<Tag[]> {
  return client.get<Tag[]>('/tags').then((r) => r.data)
}

/** Get a single tag by ID. */
export function getTag(id: number): Promise<Tag> {
  return client.get<Tag>(`/tags/${id}`).then((r) => r.data)
}

/** Create a new tag. */
export function createTag(data: TagCreate): Promise<Tag> {
  return client.post<Tag>('/tags', data).then((r) => r.data)
}

/** Update an existing tag. */
export function updateTag(id: number, data: TagUpdate): Promise<Tag> {
  return client.put<Tag>(`/tags/${id}`, data).then((r) => r.data)
}

/** Delete a tag by ID. */
export function deleteTag(id: number): Promise<void> {
  return client.delete(`/tags/${id}`).then(() => undefined)
}

/** Get all videos with a specific tag. */
export function getTagVideos(tagId: number): Promise<any[]> {
  return client.get(`/tags/${tagId}/videos`).then((r) => r.data)
}

/** Add tags to a video. */
export function addTagsToVideo(videoId: number, tagIds: number[]): Promise<void> {
  return client.post(`/tags/video/${videoId}`, { tag_ids: tagIds }).then(() => undefined)
}

/** Remove a tag from a video. */
export function removeTagFromVideo(videoId: number, tagId: number): Promise<void> {
  return client.delete(`/tags/video/${videoId}/${tagId}`).then(() => undefined)
}
