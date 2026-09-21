import api from './client'

/** 系统配置：只有 owner 读得到，也只有 owner 写得动。主题不在这里，见 api/preferences。 */
export interface Settings {
  auto_scan_enabled: boolean
  auto_scan_interval: number
  default_transcode_format: string
  thumbnail_width: number
  thumbnail_height: number
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
