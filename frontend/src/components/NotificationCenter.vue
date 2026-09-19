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
        <div class="notification-actions">
          <el-button link @click="handleMarkAllRead" :disabled="unreadCount === 0">
            全部已读
          </el-button>
          <el-button v-if="notifications.length" link class="clear-btn" @click="handleClearAll">
            {{ confirmingClear ? '确认清空' : '清空' }}
          </el-button>
        </div>
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
            <button
              class="notification-remove"
              title="删除这条通知"
              @click.stop="handleDelete(notification.id)"
            >
              &#10005;
            </button>
          </div>
        </div>
      </el-scrollbar>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Bell, CircleCheck, InfoFilled, Warning } from '@element-plus/icons-vue'
import { notificationsApi } from '@/api/notifications'
import type { Notification } from '@/api/notifications'

const notifications = ref<Notification[]>([])
const unreadCount = ref(0)
const confirmingClear = ref(false)

let clearConfirmTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  fetchNotifications()
  fetchUnreadCount()
})

onUnmounted(() => {
  if (clearConfirmTimer) clearTimeout(clearConfirmTimer)
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

async function handleDelete(id: number) {
  await notificationsApi.remove(id)
  notifications.value = notifications.value.filter((item) => item.id !== id)
  await fetchUnreadCount()
}

/** Deleting the whole list asks once, and the ask expires. */
async function handleClearAll() {
  if (!confirmingClear.value) {
    confirmingClear.value = true
    if (clearConfirmTimer) clearTimeout(clearConfirmTimer)
    clearConfirmTimer = setTimeout(() => {
      confirmingClear.value = false
    }, 4000)
    return
  }
  confirmingClear.value = false
  if (clearConfirmTimer) clearTimeout(clearConfirmTimer)

  await notificationsApi.clearAll()
  notifications.value = []
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
  background: var(--tile-bg);
  border-color: var(--glass-border-strong);
  color: var(--accent);
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
  border-radius: var(--radius-tile);
  position: relative;
  transition: background-color 0.16s ease;
}

.notification-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.clear-btn {
  color: var(--text-glass-secondary);
}

.clear-btn:hover {
  color: var(--danger-solid, var(--el-color-danger));
}

.notification-remove {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--text-glass-secondary);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.16s ease, background-color 0.16s ease;
}

.notification-item:hover .notification-remove,
.notification-remove:focus-visible {
  opacity: 1;
}

.notification-remove:hover {
  background-color: var(--tile-bg);
  color: var(--danger-solid, var(--el-color-danger));
}

.notification-item:hover {
  background-color: var(--tile-bg);
}

.notification-item.unread {
  background: var(--accent-soft);
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
