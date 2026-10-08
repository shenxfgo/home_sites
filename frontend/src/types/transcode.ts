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

/**
 * 一份转码产物，从 `GET /transcode/{id}/outputs`（#154）。
 *
 * `size_bytes` 是后端**当场**从磁盘 stat 出来的，不是库里抄的：库里那份会说谎，
 * 产物被人手工删掉腾磁盘是真会发生的事。删掉之后 `deleted_at` 才有值。
 */
export interface TranscodeProduct {
  id: number
  target_format: string
  output_path: string
  size_bytes: number | null
  created_at: string
  deleted_at: string | null
}
