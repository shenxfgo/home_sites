/** Result of a scan, matching the backend ScanResultResponse schema. */
export interface ScanResult {
  /** Set by the single-source route; the scan-all reply leaves it null. */
  source_id: number | null
  files_found: number
  new_videos: number
  subtitles_found: number
  /** The four totals below are filled only by the scan-all route. */
  sources_scanned: number | null
  total_files: number | null
  total_new_videos: number | null
  total_subtitles: number | null
}
