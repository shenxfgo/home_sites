import client from './client'
import type { ScanResult } from '@/types/scan'

/** Scan every active source. The reply carries the aggregate totals, not per-source counters. */
export function scanAll(): Promise<ScanResult> {
  return client.post<ScanResult>('/scan/all').then((r) => r.data)
}

/** Scan one source. The reply carries this source's counters; the aggregate totals stay null. */
export function scanSource(sourceId: number): Promise<ScanResult> {
  return client.post<ScanResult>(`/sources/${sourceId}/scan`).then((r) => r.data)
}
