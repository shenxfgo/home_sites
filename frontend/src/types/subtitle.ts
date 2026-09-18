/** A subtitle track of a video, matching the backend API schema. */
export interface Subtitle {
  id: number
  video_id: number
  language: string | null
  filepath: string
  label: string | null
  created_at: string
}

/** Request body for registering an existing subtitle file as a track. */
export interface SubtitleCreate {
  filepath: string
  language?: string | null
  label?: string | null
}
