<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { StarFilled, VideoCamera } from '@element-plus/icons-vue'
import { listFavorites, removeFavorite } from '@/api/favorites'
import { thumbnailUrl } from '@/api/videos'
import type { Video } from '@/types/video'

const router = useRouter()

const videos = ref<Video[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

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

async function loadFavorites() {
  loading.value = true
  try {
    const result = await listFavorites(currentPage.value, pageSize.value)
    videos.value = result.items
    total.value = result.total
  } catch (err: unknown) {
    ElMessage.error(`Failed to load favorites: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

async function handleRemoveFavorite(video: Video) {
  const title = video.title || video.filepath.split(/[/\\]/).pop() || '此视频'
  try {
    await ElMessageBox.confirm(
      `确定要将 "${title}" 从收藏中移除吗？`,
      '确认移除',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' },
    )
    await removeFavorite(video.id)
    ElMessage.success('已从收藏中移除')
    loadFavorites()
  } catch (err: unknown) {
    if (err !== 'cancel' && !(err instanceof Error && err.message === 'cancel')) {
      ElMessage.error(`Remove failed: ${err instanceof Error ? err.message : err}`)
    }
  }
}

function goToVideo(videoId: number) {
  router.push({ name: 'video-detail', params: { id: videoId } })
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadFavorites()
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  loadFavorites()
}

onMounted(loadFavorites)
</script>

<template>
  <div class="favorites-page">
    <div class="page-header">
      <h2>我的收藏</h2>
    </div>

    <!-- Empty state -->
    <el-empty
      v-if="!loading && videos.length === 0"
      description="暂无收藏视频。"
    >
      <template #image>
        <el-icon :size="64" color="#f7ba2a">
          <StarFilled />
        </el-icon>
      </template>
    </el-empty>

    <!-- Favorites grid -->
    <div v-loading="loading" class="favorites-grid">
      <el-card
        v-for="video in videos"
        :key="video.id"
        shadow="hover"
        class="favorite-card"
      >
        <!-- Thumbnail -->
        <div class="card-thumb" @click="goToVideo(video.id)">
          <img
            v-if="video.thumbnail_path"
            :src="thumbnailUrl(video.id)"
            :alt="video.title ?? 'Video'"
          />
          <div v-else class="thumb-placeholder">
            <el-icon :size="48" color="#c0c4cc">
              <VideoCamera />
            </el-icon>
          </div>
          <span v-if="video.duration != null" class="duration-badge">
            {{ formatDuration(video.duration) }}
          </span>
        </div>

        <!-- Info -->
        <div class="card-info">
          <h3
            class="video-title"
            :title="video.title || video.filepath.split(/[/\\]/).pop() || 'Untitled'"
            @click="goToVideo(video.id)"
          >
            {{ video.title || video.filepath.split(/[/\\]/).pop() || '无标题' }}
          </h3>
          <div class="video-meta">
            <span v-if="video.resolution">{{ video.resolution }}</span>
            <span v-if="video.file_size">{{ formatFileSize(video.file_size) }}</span>
          </div>
          <div class="card-actions">
            <el-button
              type="primary"
              size="small"
              @click="goToVideo(video.id)"
            >
              播放
            </el-button>
            <el-button
              type="danger"
              text
              size="small"
              @click="handleRemoveFavorite(video)"
            >
              移除
            </el-button>
          </div>
        </div>
      </el-card>
    </div>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="pagination-wrapper">
      <el-pagination
        :current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 40, 60]"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.favorites-page {
  padding: 4px 0;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.favorites-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
  min-height: 200px;
}

.favorite-card {
  overflow: hidden;
}

.card-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(124, 108, 255, 0.12), rgba(255, 107, 157, 0.12));
  margin-bottom: 12px;
  cursor: pointer;
  position: relative;
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.duration-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background-color: rgba(10, 8, 24, 0.65);
  backdrop-filter: blur(6px);
  color: #fff;
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.video-title:hover {
  color: var(--el-color-primary);
}

.video-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding: 8px 0;
}
</style>
