import client from './client'
import type { TranscodeFormat, TranscodeStatus, TranscodeResult } from '@/types/transcode'

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
