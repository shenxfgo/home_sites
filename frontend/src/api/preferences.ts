import client from './client'

/** 每个人自己的界面选择，与服务端 `/api/preferences` 同构。 */
export interface Preferences {
  theme: 'light' | 'dark' | 'auto'
}

/** Read the signed-in account's preferences. */
export function getPreferences(): Promise<Preferences> {
  return client.get<Preferences>('/preferences').then((r) => r.data)
}

/** Merge the given keys into them; omitted keys keep their stored value. */
export function updatePreferences(patch: Partial<Preferences>): Promise<Preferences> {
  return client.put<Preferences>('/preferences', patch).then((r) => r.data)
}
