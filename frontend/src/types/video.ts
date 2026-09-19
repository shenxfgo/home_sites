/** Tag associated with a video. */
export interface Tag {
  id: number
  name: string
  color: string
  video_count?: number
}

/** Request body for creating a tag. */
export interface TagCreate {
  name: string
  color?: string
}

/** Request body for updating a tag. */
export interface TagUpdate {
  name?: string
  color?: string
}

/** A video record matching the backend API schema. */
export interface Video {
  id: number
  source_id: number
  filepath: string
  title: string | null
  description: string | null
  duration: number | null
  file_size: number | null
  format: string | null
  resolution: string | null
  thumbnail_path: string | null
  rating: number
  view_count: number
  /** Discovered by a recent scan and not played yet. */
  is_new: boolean
  last_played_at: string | null
  created_at: string
  updated_at: string
  tags: Tag[]
}

/** Paginated video list response. */
export interface VideoListResponse {
  items: Video[]
  total: number
  page: number
  page_size: number
}

/** Query parameters for listing videos. */
export interface VideoQueryParams {
  source_id?: number
  tag_id?: number
  search?: string
  page?: number
  page_size?: number
}

/** Request body for updating a video (all fields optional). */
export interface VideoUpdate {
  title?: string | null
  description?: string | null
  rating?: number | null
  tag_ids?: number[] | null
}
