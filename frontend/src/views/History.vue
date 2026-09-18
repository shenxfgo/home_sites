<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoCamera, Clock } from '@element-plus/icons-vue'
import {
  listHistory,
  getContinueList,
  deleteHistory,
} from '@/api/history'
import type { HistoryItem } from '@/api/history'
import { thumbnailUrl } from '@/api/videos'
import type { Video } from '@/types/video'

const router = useRouter()

const historyItems = ref<HistoryItem[]>([])
const continueVideos = ref<Video[]>([])
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

/** Format date. */
function formatDate(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

/** Format progress as MM:SS or HH:MM:SS. */
function formatProgress(seconds: number): string {
  return formatDuration(seconds)
}

async function loadHistory() {
  loading.value = true
  try {
    const result = await listHistory(currentPage.value, pageSize.value)
    historyItems.value = result.items
    total.value = result.total
  } catch (err: unknown) {
    ElMessage.error(`Failed to load history: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

async function loadContinueList() {
  try {
    continueVideos.value = await getContinueList()
  } catch {
    // Silently ignore
  }
}

async function handleDelete(item: HistoryItem) {
  try {
    await ElMessageBox.confirm(
      '确定要删除这条播放记录吗？',
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await deleteHistory(item.id)
    ElMessage.success('播放记录已删除')
    loadHistory()
  } catch (err: unknown) {
    if (err !== 'cancel' && !(err instanceof Error && err.message === 'cancel')) {
      ElMessage.error(`Delete failed: ${err instanceof Error ? err.message : err}`)
    }
  }
}

function goToVideo(videoId: number) {
  router.push({ name: 'video-detail', params: { id: videoId } })
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadHistory()
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  loadHistory()
}

onMounted(() => {
  loadHistory()
  loadContinueList()
})
</script>

<template>
  <div class="history-page">
    <!-- Continue Watching Section -->
    <div v-if="continueVideos.length > 0" class="section">
      <h3 class="section-title">继续观看</h3>
      <div class="continue-grid">
        <el-card
          v-for="video in continueVideos"
          :key="video.id"
          shadow="hover"
          class="continue-card"
          @click="goToVideo(video.id)"
        >
          <div class="continue-thumb">
            <img
              v-if="video.thumbnail_path"
              :src="thumbnailUrl(video.id)"
              :alt="video.title ?? 'Video'"
            />
            <div v-else class="thumb-placeholder">
              <el-icon :size="36" color="#c0c4cc">
                <VideoCamera />
              </el-icon>
            </div>
          </div>
          <div class="continue-info">
            <h4 class="continue-title">{{ video.title || video.filepath.split(/[/\\]/).pop() || '无标题' }}</h4>
            <span class="continue-meta">
              {{ video.resolution || '' }}
              <template v-if="video.duration"> &middot; {{ formatDuration(video.duration) }}</template>
            </span>
          </div>
        </el-card>
      </div>
    </div>

    <!-- History List Section -->
    <div class="section">
      <h3 class="section-title">观看历史</h3>

      <!-- Empty state -->
      <el-empty
        v-if="!loading && historyItems.length === 0"
        description="暂无观看历史。"
      >
        <template #image>
          <el-icon :size="64" color="var(--el-color-primary)">
            <Clock />
          </el-icon>
        </template>
      </el-empty>

      <!-- History table -->
      <el-table
        v-loading="loading"
        :data="historyItems"
        style="width: 100%"
        empty-description="暂无历史记录"
      >
        <el-table-column label="视频" min-width="300">
          <template #default="{ row }">
            <div
              class="video-link"
              @click="goToVideo(row.video_id)"
            >
              <el-icon><VideoCamera /></el-icon>
              <span>{{ row.video_title || `视频 #${row.video_id}` }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="120" align="center">
          <template #default="{ row }">
            <span>{{ formatProgress(row.progress) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.completed" type="success" size="small">已完成</el-tag>
            <el-tag v-else type="warning" size="small">播放中</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="播放时间" width="180" align="center">
          <template #default="{ row }">
            <span class="date-text">{{ formatDate(row.played_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="80" align="center">
          <template #default="{ row }">
            <el-button
              type="danger"
              text
              size="small"
              @click.stop="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

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
  </div>
</template>

<style scoped>
.history-page {
  padding: 4px 0;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px 0;
}

/* Continue Watching */
.continue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.continue-card {
  cursor: pointer;
  transition: transform 0.2s;
  overflow: hidden;
}

.continue-card:hover {
  transform: translateY(-2px);
}

.continue-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(124, 108, 255, 0.12), rgba(255, 107, 157, 0.12));
  margin-bottom: 8px;
}

.continue-thumb img {
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

.continue-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.continue-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.continue-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* History table */
.video-link {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--el-color-primary);
}

.video-link:hover {
  text-decoration: underline;
}

.date-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding: 8px 0;
}
</style>
