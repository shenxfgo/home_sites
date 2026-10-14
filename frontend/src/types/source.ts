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

/**
 * Request body for creating a video source.
 *
 * `scan_interval` 可以整个不带：省略时后端读系统配置里的 `auto_scan_interval`
 * （#151 甲）。界面上它是预填好的一个数，不是必填的另一种写法。
 */
export interface SourceCreate {
  name: string
  path: string
  type: SourceType
  scan_interval?: number
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
  minio: 'S3 / MinIO',
}
