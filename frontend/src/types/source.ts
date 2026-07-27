/** Video source types matching the backend API schema. */

export type SourceType = 'local' | 'nas' | 'minio'

/** A video source configuration. */
export interface Source {
  id: number
  name: string
  path: string
  type: SourceType
  scan_interval: number
  last_scan_at: string | null
  is_active: boolean
  created_at: string
}

/** Request body for creating a video source. */
export interface SourceCreate {
  name: string
  path: string
  type: SourceType
  scan_interval: number
  is_active: boolean
}

/** Request body for updating a video source (all fields optional). */
export interface SourceUpdate {
  name?: string
  path?: string
  type?: SourceType
  scan_interval?: number
  is_active?: boolean
}

/** Display-friendly label for source types. */
export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  local: '本地',
  nas: 'NAS',
  minio: 'MinIO',
}

/** Icon name for each source type. */
export const SOURCE_TYPE_ICONS: Record<SourceType, string> = {
  local: 'FolderOpened',
  nas: 'Connection',
  minio: 'Box',
}
