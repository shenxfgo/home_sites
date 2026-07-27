<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  VideoCamera,
  Edit,
  Delete,
  Star,
  StarFilled,
  VideoPlay,
  Collection,
  CollectionTag,
  Setting,
  Plus,
} from '@element-plus/icons-vue'
import {
  getVideo,
  updateVideo,
  deleteVideo,
} from '@/api/videos'
import {
  checkFavorite,
  addFavorite,
  removeFavorite,
} from '@/api/favorites'
import { listTags, addTagsToVideo, removeTagFromVideo } from '@/api/tags'
import type { Video, VideoUpdate } from '@/types/video'
import type { Tag } from '@/types/video'
import VideoPlayer from '@/components/VideoPlayer.vue'

const route = useRoute()
const router = useRouter()

const video = ref<Video | null>(null)
const loading = ref(true)
const editing = ref(false)
const isPlaying = ref(false)
const isFavorite = ref(false)
const editForm = ref<{ title: string; description: string; rating: number }>({
  title: '',
  description: '',
  rating: 0,
})

// Tag management
const allTags = ref<Tag[]>([])
const selectedTagIds = ref<number[]>([])
const showTagDialog = ref(false)

const videoId = computed(() => Number(route.params.id))

/** Get the video stream URL. */
function getVideoUrl(): string {
  if (!video.value) return ''
  // Vite proxy forwards /api to backend
  return `/api/videos/${video.value.id}/stream`
}

/** Format duration in seconds to HH:MM:SS or MM:SS. */
function formatDuration(seconds: number | null): string {
  if (seconds == null) return 'N/A'
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
  if (bytes == null) return 'N/A'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/** Format date. */
function formatDate(iso: string | null): string {
  if (!iso) return '从未'
  return new Date(iso).toLocaleString()
}

async function loadVideo() {
  loading.value = true
  try {
    video.value = await getVideo(videoId.value)
    // Load favorite status
    try {
      isFavorite.value = await checkFavorite(videoId.value)
    } catch {
      // Silently ignore favorite check failure
    }
  } catch (err: unknown) {
    ElMessage.error(`Failed to load video: ${err instanceof Error ? err.message : err}`)
    router.push({ name: 'home' })
  } finally {
    loading.value = false
  }
}

async function loadAllTags() {
  try {
    allTags.value = await listTags()
  } catch {
    // Silently ignore
  }
}

function openTagDialog() {
  if (!video.value) return
  selectedTagIds.value = video.value.tags.map(t => t.id)
  showTagDialog.value = true
}

async function handleSaveTags() {
  if (!video.value) return

  const currentTagIds = video.value.tags.map(t => t.id)
  const tagsToAdd = selectedTagIds.value.filter(id => !currentTagIds.includes(id))
  const tagsToRemove = currentTagIds.filter(id => !selectedTagIds.value.includes(id))

  try {
    if (tagsToAdd.length > 0) {
      await addTagsToVideo(video.value.id, tagsToAdd)
    }
    if (tagsToRemove.length > 0) {
      for (const tagId of tagsToRemove) {
        await removeTagFromVideo(video.value.id, tagId)
      }
    }
    // Reload video to get updated tags
    video.value = await getVideo(videoId.value)
    showTagDialog.value = false
    ElMessage.success('标签已更新')
  } catch (err: unknown) {
    ElMessage.error(`Failed: ${err instanceof Error ? err.message : err}`)
  }
}

async function toggleFavorite() {
  if (!video.value) return
  try {
    if (isFavorite.value) {
      await removeFavorite(video.value.id)
      isFavorite.value = false
      ElMessage.success('已取消收藏')
    } else {
      await addFavorite(video.value.id)
      isFavorite.value = true
      ElMessage.success('已添加到收藏')
    }
  } catch (err: unknown) {
    ElMessage.error(`Failed: ${err instanceof Error ? err.message : err}`)
  }
}

function startEdit() {
  if (!video.value) return
  editForm.value = {
    title: video.value.title ?? '',
    description: video.value.description ?? '',
    rating: video.value.rating,
  }
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  if (!video.value) return
  const data: VideoUpdate = {
    title: editForm.value.title || null,
    description: editForm.value.description || null,
    rating: editForm.value.rating,
  }
  try {
    video.value = await updateVideo(video.value.id, data)
    editing.value = false
    ElMessage.success('视频信息已更新')
  } catch (err: unknown) {
    ElMessage.error(`Update failed: ${err instanceof Error ? err.message : err}`)
  }
}

async function handleDelete() {
  if (!video.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除 "${video.value.title ?? video.value.filepath}" 吗？`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await deleteVideo(video.value.id)
    ElMessage.success('视频已删除')
    router.push({ name: 'home' })
  } catch (err: unknown) {
    if (err !== 'cancel' && !(err instanceof Error && err.message === 'cancel')) {
      ElMessage.error(`Delete failed: ${err instanceof Error ? err.message : err}`)
    }
  }
}

async function handlePlay() {
  isPlaying.value = true
}

function handlePlayerEnded() {
  isPlaying.value = false
}

function handlePlayerError(error: Event) {
  console.error('Player error:', error)
  ElMessage.error('视频播放失败')
}

onMounted(() => {
  loadVideo()
  loadAllTags()
})
</script>

<template>
  <div v-loading="loading" class="detail-page">
    <!-- Back button -->
    <div class="top-bar">
      <el-button :icon="ArrowLeft" text @click="router.push({ name: 'home' })">
        返回列表
      </el-button>
    </div>

    <template v-if="video">
      <div class="detail-content">
        <!-- Video Player or Thumbnail -->
        <div v-if="isPlaying" class="player-area">
          <VideoPlayer
            :video-id="video.id"
            :video-url="getVideoUrl()"
            @ended="handlePlayerEnded"
            @error="handlePlayerError"
          />
        </div>
        <div v-else class="preview-area" @click="handlePlay">
          <div v-if="video.thumbnail_path" class="preview-thumbnail">
            <img :src="video.thumbnail_path" :alt="video.title ?? 'Video'" />
            <div class="play-overlay">
              <div class="play-button-large">
                <el-icon :size="48" color="white">
                  <VideoPlay />
                </el-icon>
              </div>
            </div>
          </div>
          <div v-else class="preview-placeholder">
            <el-icon :size="72" color="#c0c4cc">
              <VideoCamera />
            </el-icon>
            <span>暂无预览</span>
            <el-button type="primary" :icon="VideoPlay" @click.stop="handlePlay">
              播放视频
            </el-button>
          </div>
        </div>

        <!-- Info section -->
        <div class="info-section">
          <template v-if="!editing">
            <div class="header-row">
              <h1 class="video-title">{{ video.title || video.filepath.split(/[/\\]/).pop() || '无标题' }}</h1>
              <div class="action-buttons">
                <el-button
                  v-if="!isPlaying"
                  :icon="VideoPlay"
                  type="primary"
                  @click="handlePlay"
                >
                  播放
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  @click="isPlaying = false"
                >
                  停止
                </el-button>
                <el-button
                  :icon="isFavorite ? CollectionTag : Collection"
                  :type="isFavorite ? 'warning' : 'default'"
                  @click="toggleFavorite"
                >
                  {{ isFavorite ? '已收藏' : '收藏' }}
                </el-button>
                <el-button :icon="Setting" @click="router.push({ name: 'transcode', params: { id: video.id } })">
                  转码
                </el-button>
                <el-button :icon="Edit" @click="startEdit">
                  编辑
                </el-button>
                <el-button :icon="Delete" type="danger" @click="handleDelete">
                  删除
                </el-button>
              </div>
            </div>

            <!-- Rating -->
            <div class="rating-row">
              <span class="label">评分：</span>
              <template v-for="i in 5" :key="i">
                <el-icon
                  :size="18"
                  class="star-icon"
                  :class="{ filled: i <= video.rating }"
                >
                  <StarFilled v-if="i <= video.rating" />
                  <Star v-else />
                </el-icon>
              </template>
              <span class="rating-text">{{ video.rating }}/5</span>
            </div>

            <!-- Description -->
            <p v-if="video.description" class="description">{{ video.description }}</p>

            <!-- Tags -->
            <div class="tags-section">
              <span class="label">标签：</span>
              <div class="tags-list">
                <el-tag
                  v-for="tag in video.tags"
                  :key="tag.id"
                  :color="tag.color"
                  effect="dark"
                >
                  {{ tag.name }}
                </el-tag>
                <el-button
                  :icon="Plus"
                  size="small"
                  circle
                  @click="openTagDialog"
                />
              </div>
            </div>

            <!-- Metadata -->
            <div class="meta-grid">
              <div class="meta-item">
                <span class="label">时长</span>
                <span>{{ formatDuration(video.duration) }}</span>
              </div>
              <div class="meta-item">
                <span class="label">分辨率</span>
                <span>{{ video.resolution || '未知' }}</span>
              </div>
              <div class="meta-item">
                <span class="label">格式</span>
                <span>{{ video.format || '未知' }}</span>
              </div>
              <div class="meta-item">
                <span class="label">文件大小</span>
                <span>{{ formatFileSize(video.file_size) }}</span>
              </div>
              <div class="meta-item">
                <span class="label">播放次数</span>
                <span>{{ video.view_count }}</span>
              </div>
              <div class="meta-item">
                <span class="label">上次播放</span>
                <span>{{ formatDate(video.last_played_at) }}</span>
              </div>
              <div class="meta-item full-width">
                <span class="label">文件路径</span>
                <span class="filepath">{{ video.filepath }}</span>
              </div>
              <div class="meta-item">
                <span class="label">创建时间</span>
                <span>{{ formatDate(video.created_at) }}</span>
              </div>
              <div class="meta-item">
                <span class="label">更新时间</span>
                <span>{{ formatDate(video.updated_at) }}</span>
              </div>
            </div>
          </template>

          <!-- Edit mode -->
          <template v-else>
            <h2 class="edit-title">编辑视频信息</h2>
            <el-form label-width="100px" label-position="right" class="edit-form">
              <el-form-item label="标题">
                <el-input
                  v-model="editForm.title"
                  placeholder="视频标题"
                  maxlength="512"
                />
              </el-form-item>
              <el-form-item label="描述">
                <el-input
                  v-model="editForm.description"
                  type="textarea"
                  :rows="3"
                  placeholder="视频描述"
                />
              </el-form-item>
              <el-form-item label="评分">
                <div class="edit-rating">
                  <template v-for="i in 5" :key="i">
                    <el-icon
                      :size="22"
                      class="star-icon editable"
                      :class="{ filled: i <= editForm.rating }"
                      @click="editForm.rating = i === editForm.rating ? 0 : i"
                    >
                      <StarFilled v-if="i <= editForm.rating" />
                      <Star v-else />
                    </el-icon>
                  </template>
                </div>
              </el-form-item>
            </el-form>
            <div class="edit-actions">
              <el-button @click="cancelEdit">取消</el-button>
              <el-button type="primary" @click="saveEdit">保存</el-button>
            </div>
          </template>
        </div>
      </div>
    </template>

    <!-- Tag Edit Dialog -->
    <el-dialog
      v-model="showTagDialog"
      title="编辑标签"
      width="400px"
    >
      <el-checkbox-group v-model="selectedTagIds">
        <div v-for="tag in allTags" :key="tag.id" class="tag-checkbox-item">
          <el-checkbox :label="tag.id">
            <el-tag :color="tag.color" effect="dark" size="small">
              {{ tag.name }}
            </el-tag>
          </el-checkbox>
        </div>
      </el-checkbox-group>

      <template #footer>
        <el-button @click="showTagDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveTags">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-page {
  padding: 4px 0;
}

.top-bar {
  margin-bottom: 16px;
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.player-area {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
}

.preview-area {
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: 480px;
  border-radius: 8px;
  overflow: hidden;
  background-color: #f5f7fa;
  cursor: pointer;
  position: relative;
}

.preview-thumbnail {
  width: 100%;
  height: 100%;
  position: relative;
}

.preview-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 0.3s;
}

.preview-area:hover .play-overlay {
  opacity: 1;
}

.play-button-large {
  width: 80px;
  height: 80px;
  background: rgba(64, 158, 255, 0.9);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s;
}

.preview-area:hover .play-button-large {
  transform: scale(1.1);
}

.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
}

.info-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.video-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.star-icon {
  color: #dcdfe6;
  cursor: default;
}

.star-icon.filled {
  color: #f7ba2a;
}

.star-icon.editable {
  cursor: pointer;
}

.rating-text {
  margin-left: 8px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.description {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
  white-space: pre-wrap;
}

.tags-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tags-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.label {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 8px;
  padding: 16px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-item.full-width {
  grid-column: 1 / -1;
}

.meta-item .label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.filepath {
  word-break: break-all;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* Edit mode */
.edit-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.edit-form {
  max-width: 600px;
}

.edit-rating {
  display: flex;
  gap: 4px;
  align-items: center;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

/* Tag dialog */
.tag-checkbox-item {
  margin-bottom: 12px;
}

.tag-checkbox-item:last-child {
  margin-bottom: 0;
}
</style>
