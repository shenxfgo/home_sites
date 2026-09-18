<template>
  <div class="notification-center">
    <el-popover placement="bottom" :width="400" trigger="click">
      <template #reference>
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
          <el-button :icon="Bell" circle />
        </el-badge>
      </template>

      <div class="notification-header">
        <span>通知</span>
        <el-button link @click="handleMarkAllRead" :disabled="unreadCount === 0">
          全部已读
        </el-button>
      </div>

      <el-scrollbar height="400px">
        <div v-if="notifications.length === 0" class="empty-state">
          暂无通知
        </div>
        <div v-else>
          <div
            v-for="notification in notifications"
            :key="notification.id"
            class="notification-item"
            :class="{ unread: !notification.read }"
            @click="handleMarkRead(notification)"
          >
            <el-icon class="notification-icon" :color="getIconColor(notification.type)">
              <component :is="getIcon(notification.type)" />
            </el-icon>
            <div class="notification-content">
              <div class="notification-title">{{ notification.title }}</div>
              <div class="notification-message">{{ notification.message }}</div>
              <div class="notification-time">{{ formatTime(notification.created_at) }}</div>
            </div>
          </div>
        </div>
      </el-scrollbar>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Bell, CircleCheck, InfoFilled, Warning } from '@element-plus/icons-vue'
import { notificationsApi } from '@/api/notifications'
import type { Notification } from '@/api/notifications'

const notifications = ref<Notification[]>([])
const unreadCount = ref(0)

onMounted(() => {
  fetchNotifications()
  fetchUnreadCount()
})

async function fetchNotifications() {
  const response = await notificationsApi.list(1, 50)
  notifications.value = response.items
}

async function fetchUnreadCount() {
  unreadCount.value = await notificationsApi.getUnreadCount()
}

async function handleMarkRead(notification: Notification) {
  if (!notification.read) {
    await notificationsApi.markRead(notification.id)
    notification.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }
}

async function handleMarkAllRead() {
  await notificationsApi.markAllRead()
  notifications.value.forEach(n => n.read = true)
  unreadCount.value = 0
}

function getIcon(type: string) {
  const icons: Record<string, any> = {
    scan_complete: CircleCheck,
    new_video: InfoFilled,
    error: Warning,
  }
  return icons[type] || InfoFilled
}

function getIconColor(type: string): string {
  const colors: Record<string, string> = {
    scan_complete: '#67c23a',
    new_video: '#409eff',
    error: '#f56c6c',
  }
  return colors[type] || '#909399'
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.notification-badge :deep(.el-button) {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--text-glass);
}

.notification-badge :deep(.el-button:hover) {
  background: rgba(124, 108, 255, 0.12);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 4px;
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: 8px;
  color: var(--text-glass);
}

.notification-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  cursor: pointer;
  border-radius: 14px;
  transition: background-color 0.2s;
}

.notification-item:hover {
  background-color: rgba(124, 108, 255, 0.1);
}

.notification-item.unread {
  background: linear-gradient(135deg, rgba(124, 108, 255, 0.14), rgba(255, 107, 157, 0.08));
}

.notification-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-glass);
}

.notification-message {
  font-size: 13px;
  color: var(--text-glass-secondary);
  margin-bottom: 4px;
}

.notification-time {
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.empty-state {
  text-align: center;
  color: var(--text-glass-secondary);
  padding: 40px 0;
}
</style>
