import api from './client'

export interface Settings {
  auto_scan_enabled: boolean
  auto_scan_interval: number
  default_transcode_format: string
  thumbnail_width: number
  thumbnail_height: number
  theme: string
}

/** Get all application settings. */
export async function getSettings(): Promise<Settings> {
  const response = await api.get('/settings')
  return response.data
}

/** Update all application settings. */
export async function updateSettings(data: Settings): Promise<Settings> {
  const response = await api.put('/settings', data)
  return response.data
}

/** Get a single setting by key. */
export async function getSetting(key: string): Promise<{ key: string; value: string }> {
  const response = await api.get(`/settings/${key}`)
  return response.data
}

/** Update a single setting. */
export async function updateSetting(key: string, value: string): Promise<{ key: string; value: string }> {
  const response = await api.put(`/settings/${key}`, { value })
  return response.data
}
