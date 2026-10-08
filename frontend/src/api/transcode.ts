import client from './client'
import type {
  TranscodeFormat,
  TranscodeProduct,
  TranscodeResult,
  TranscodeStatus,
} from '@/types/transcode'

/** List the formats FFmpeg can transcode to. */
export function listTranscodeFormats(): Promise<TranscodeFormat[]> {
  return client.get<TranscodeFormat[]>('/transcode/formats').then((r) => r.data)
}

/** Get the current state of a video's transcode job. */
export function getTranscodeStatus(videoId: number): Promise<TranscodeStatus> {
  return client.get<TranscodeStatus>(`/transcode/${videoId}/status`).then((r) => r.data)
}

/** Queue a transcode of the video to the given format. */
export function startTranscode(videoId: number, targetFormat: string): Promise<TranscodeResult> {
  return client
    .post<TranscodeResult>(`/transcode/${videoId}`, { target_format: targetFormat })
    .then((r) => r.data)
}

/** Stop a running transcode job. The route answers 204 with no body. */
export function cancelTranscode(videoId: number): Promise<void> {
  return client.post(`/transcode/${videoId}/cancel`).then(() => undefined)
}

/**
 * This video's products, newest first.
 *
 * The backend stats every file on the way out, so a `size_bytes` of `null` (and a
 * filled `deleted_at`) means somebody removed the file from disk after the job ended.
 */
export function listTranscodeProducts(videoId: number): Promise<TranscodeProduct[]> {
  return client.get<TranscodeProduct[]>(`/transcode/${videoId}/outputs`).then((r) => r.data)
}
