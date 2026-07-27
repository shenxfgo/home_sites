import client from './client'
import type { Source, SourceCreate, SourceUpdate } from '@/types/source'

/** List all video sources. */
export function listSources(activeOnly = false): Promise<Source[]> {
  return client
    .get<Source[]>('/sources', { params: { active_only: activeOnly } })
    .then((r) => r.data)
}

/** Create a new video source. */
export function createSource(data: SourceCreate): Promise<Source> {
  return client.post<Source>('/sources', data).then((r) => r.data)
}

/** Get a single video source by ID. */
export function getSource(id: number): Promise<Source> {
  return client.get<Source>(`/sources/${id}`).then((r) => r.data)
}

/** Update an existing video source. */
export function updateSource(id: number, data: SourceUpdate): Promise<Source> {
  return client.put<Source>(`/sources/${id}`, data).then((r) => r.data)
}

/** Delete a video source by ID. */
export function deleteSource(id: number): Promise<void> {
  return client.delete(`/sources/${id}`).then(() => undefined)
}
