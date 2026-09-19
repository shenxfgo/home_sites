import client from './client'
import type {
  MediaStreams,
  Subtitle,
  SubtitleCreate,
} from '@/types/subtitle'

/** List the subtitle tracks of a video. */
export function listSubtitles(videoId: number): Promise<Subtitle[]> {
  return client.get<Subtitle[]>(`/videos/${videoId}/subtitles`).then((r) => r.data)
}

/** Register a subtitle file that sits next to the video. */
export function addSubtitle(videoId: number, data: SubtitleCreate): Promise<Subtitle> {
  return client
    .post<Subtitle>(`/videos/${videoId}/subtitles`, data)
    .then((r) => r.data)
}

/** Remove a subtitle track from a video. */
export function removeSubtitle(videoId: number, subtitleId: number): Promise<void> {
  return client
    .delete(`/videos/${videoId}/subtitles/${subtitleId}`)
    .then(() => undefined)
}

/** Build the WebVTT URL a `<track>` element renders. */
export function subtitleTrackUrl(videoId: number, subtitleId: number): string {
  return `/api/videos/${videoId}/subtitles/${subtitleId}/stream`
}

/** Ask ffprobe what tracks are muxed inside the video file. */
export function listMediaStreams(videoId: number): Promise<MediaStreams> {
  return client
    .get<MediaStreams>(`/videos/${videoId}/subtitles/streams`)
    .then((r) => r.data)
}

/** Build the WebVTT URL for one embedded track, extracted on demand. */
export function embeddedSubtitleTrackUrl(videoId: number, streamIndex: number): string {
  return `/api/videos/${videoId}/subtitles/embedded/${streamIndex}/stream`
}
