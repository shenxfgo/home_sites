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

/** A subtitle track muxed into the video file itself. */
export interface EmbeddedSubtitleTrack {
  stream_index: number
  position: number
  codec: string
  language: string | null
  label: string
  /** False for bitmap tracks (PGS/DVD/DVB), which cannot become WebVTT. */
  supported: boolean
}

/** An audio track inside the container, listed for information only. */
export interface AudioTrack {
  stream_index: number
  position: number
  codec: string
  language: string | null
  label: string
  default: boolean
}

/** What ffprobe found inside the container. */
export interface MediaStreams {
  /** False when the file could not be read at all, which is not "no tracks". */
  probed: boolean
  container: string | null
  subtitles: EmbeddedSubtitleTrack[]
  audio: AudioTrack[]
}
