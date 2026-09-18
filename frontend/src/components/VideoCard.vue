<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { VideoCamera, Star, StarFilled } from '@element-plus/icons-vue'
import { thumbnailUrl } from '@/api/videos'
import type { Video } from '@/types/video'

const props = defineProps<{
  video: Video
}>()

const router = useRouter()

/** Format duration in seconds to HH:MM:SS or MM:SS. */
function formatDuration(seconds: number | null): string {
  if (seconds == null) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Format file size in bytes to human-readable string. */
function formatFileSize(bytes: number | null): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/** Determine new-video badge based on created_at. */
const newBadge = computed<{ label: string; type: 'danger' | 'warning' | 'info' } | null>(() => {
  const created = new Date(props.video.created_at)
  const now = new Date()
  const diffMs = now.getTime() - created.getTime()
  const diffHours = diffMs / (1000 * 60 * 60)

  if (diffHours < 24) {
    return { label: '新', type: 'danger' }
  }
  if (diffHours < 24 * 7) {
    return { label: '本周', type: 'warning' }
  }
  return null
})

/** Computed display title. */
const displayTitle = computed(() => props.video.title || props.video.filepath.split(/[/\\]/).pop() || '无标题')

/** Display tags (limit to 3). */
const displayTags = computed(() => props.video.tags.slice(0, 3))

function goToDetail() {
  router.push({ name: 'video-detail', params: { id: props.video.id } })
}
</script>

<template>
  <el-card shadow="hover" class="video-card" @click="goToDetail">
    <!-- Thumbnail area -->
    <div class="thumbnail-area">
      <img
        v-if="video.thumbnail_path"
        :src="thumbnailUrl(video.id)"
        :alt="displayTitle"
        class="thumbnail-img"
      />
      <div v-else class="thumbnail-placeholder">
        <el-icon :size="48" color="#c0c4cc">
          <VideoCamera />
        </el-icon>
      </div>

      <!-- Duration badge -->
      <span v-if="video.duration != null" class="duration-badge">
        {{ formatDuration(video.duration) }}
      </span>

      <!-- New badge -->
      <el-tag
        v-if="newBadge"
        :type="newBadge.type"
        size="small"
        class="new-badge"
        effect="dark"
      >
        {{ newBadge.label }}
      </el-tag>
    </div>

    <!-- Info area -->
    <div class="card-info">
      <h3 class="video-title" :title="displayTitle">{{ displayTitle }}</h3>

      <div class="video-meta">
        <span v-if="video.resolution" class="resolution">{{ video.resolution }}</span>
        <span v-if="video.file_size" class="file-size">{{ formatFileSize(video.file_size) }}</span>
      </div>

      <!-- Rating stars -->
      <div class="rating-row">
        <template v-for="i in 5" :key="i">
          <el-icon :size="14" class="star-icon" :class="{ filled: i <= video.rating }">
            <StarFilled v-if="i <= video.rating" />
            <Star v-else />
          </el-icon>
        </template>
        <span class="view-count">{{ video.view_count }} 次播放</span>
      </div>

      <!-- Tags -->
      <div v-if="displayTags.length" class="tag-row">
        <el-tag
          v-for="tag in displayTags"
          :key="tag.id"
          size="small"
          :color="tag.color"
          class="tag-item"
          effect="dark"
        >
          {{ tag.name }}
        </el-tag>
        <el-tag v-if="video.tags.length > 3" size="small" type="info" class="tag-item">
          +{{ video.tags.length - 3 }}
        </el-tag>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.video-card {
  cursor: pointer;
  overflow: hidden;
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border) !important;
  border-radius: 20px !important;
  box-shadow: var(--glass-shadow) !important;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.25s ease;
}

.video-card:hover {
  transform: translateY(-6px) scale(1.01);
  box-shadow: var(--glass-shadow-hover) !important;
}

.video-card :deep(.el-card__body) {
  padding: 14px;
}

.thumbnail-area {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background-color: rgba(124, 108, 255, 0.08);
  border-radius: 14px;
  margin-bottom: 12px;
}

.thumbnail-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.35s ease;
}

.video-card:hover .thumbnail-img {
  transform: scale(1.05);
}

.thumbnail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(124, 108, 255, 0.12), rgba(255, 107, 157, 0.12));
}

.duration-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background-color: rgba(10, 8, 24, 0.65);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  color: #fff;
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}

.new-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  font-weight: 600;
  border-radius: 999px !important;
  border: none !important;
  background: var(--grad-warm) !important;
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.video-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-glass);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.star-icon {
  color: #dcdfe6;
}

.star-icon.filled {
  color: #f7ba2a;
}

.view-count {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.tag-item {
  color: #fff;
  border: none;
}
</style>
