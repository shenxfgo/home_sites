import apiClient from './client'

export interface Notification {
  id: number
  type: string
  title: string
  message: string
  data: Record<string, any> | null
  read: boolean
  created_at: string
}

export interface NotificationListResponse {
  items: Notification[]
  total: number
  page: number
  page_size: number
}

export const notificationsApi = {
  async list(page = 1, pageSize = 20): Promise<NotificationListResponse> {
    const response = await apiClient.get('/notifications', { params: { page, page_size: pageSize } })
    return response.data
  },

  async getUnreadCount(): Promise<number> {
    const response = await apiClient.get('/notifications/unread')
    return response.data.count
  },

  async markRead(id: number): Promise<void> {
    await apiClient.post(`/notifications/${id}/read`)
  },

  async markAllRead(): Promise<void> {
    await apiClient.post('/notifications/read-all')
  },

  async remove(id: number): Promise<void> {
    await apiClient.delete(`/notifications/${id}`)
  },

  async clearAll(): Promise<void> {
    await apiClient.delete('/notifications')
  },
}
