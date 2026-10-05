/** Transcode types matching the backend API schema. */

/** One supported output format, from `GET /transcode/formats`. */
export interface TranscodeFormat {
  format: string
  codec: string
  extension: string
}

/** Live state of a transcode job, from `GET /transcode/{id}/status`. */
export interface TranscodeStatus {
  video_id: number
  is_transcoding: boolean
  status: string
  progress: number
  target_format: string | null
  output_path: string | null
  error: string | null
}

/** Receipt from starting a job: these four are already decided when it answers. */
export interface TranscodeResult {
  video_id: number
  status: string
  target_format: string
  output_path: string
}
