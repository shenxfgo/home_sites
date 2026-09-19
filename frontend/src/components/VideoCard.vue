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

/** Computed display title. */
const displayTitle = computed(() => props.video.title || props.video.filepath.split(/[/\\]/).pop() || '无标题')

/** Display tags (limit to 3). */
const displayTags = computed(() => props.video.tags.slice(0, 3))

/** Share of the title the history row reached, or null when there is nothing to resume. */
const resumeRatio = computed(() => {
  const { progress, duration } = props.video
  if (!progress || !duration || duration <= 0) return null
  const ratio = progress / duration
  return ratio >= 0.995 ? null : Math.min(1, ratio)
})

/** Coordinates the scan parsed out of the filename, e.g. S01E02 or 第12集. */
const episodeLabel = computed(() => {
  const { season, episode } = props.video
  if (episode == null) return null
  if (season == null) return `第${episode}集`
  return `S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`
})

function goToDetail() {
  router.push({ name: 'video-detail', params: { id: props.video.id } })
}
</script>

<template>
  <el-card shadow="hover" class="video-card" @click="goToDetail">
    <!-- Thumbnail area -->
    <div class="thumbnail-area" :class="{ 'is-missing': video.is_missing }">
      <img
        v-if="video.thumbnail_path"
        :src="thumbnailUrl(video.id)"
        :alt="displayTitle"
        class="thumbnail-img"
      />
      <div v-else class="thumbnail-placeholder">
        <el-icon :size="48" color="var(--text-glass-secondary)">
          <VideoCamera />
        </el-icon>
      </div>

      <!-- Duration badge -->
      <span v-if="video.duration != null" class="duration-badge">
        {{ formatDuration(video.duration) }}
      </span>

      <!-- Which episode of its series this file is -->
      <span v-if="episodeLabel" class="episode-badge">{{ episodeLabel }}</span>

      <!-- Where the last playback stopped -->
      <span
        v-if="resumeRatio"
        class="resume-bar"
        :style="{ width: resumeRatio * 100 + '%' }"
      />

      <!-- New badge: set by the scan and cleared by the first play -->
      <el-tag
        v-if="video.is_new && !video.is_missing"
        type="danger"
        size="small"
        class="new-badge"
        effect="dark"
      >
        新
      </el-tag>

      <!-- The scan could not find the file any more -->
      <span v-else-if="video.is_missing" class="missing-badge">丢失</span>
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
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  transition: transform 0.18s ease-out;
}

.video-card:hover {
  transform: translateY(-2px);
}

.video-card :deep(.el-card__body) {
  padding: 0;
}

.thumbnail-area {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background-color: var(--tile-bg);
  border-radius: var(--radius-tile);
  margin-bottom: 10px;
  transition: box-shadow 0.18s ease-out;
}

.video-card:hover .thumbnail-area {
  box-shadow: var(--glass-shadow-hover);
}

.thumbnail-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.35s ease;
}

.video-card:hover .thumbnail-img {
  transform: scale(1.04);
}

.thumbnail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--tile-bg);
}

.duration-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background-color: var(--overlay-badge);
  color: #fff;
  font-size: 12px;
  padding: 2px 7px;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}

.new-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  font-weight: 600;
  border-radius: 6px !important;
  border: none !important;
  background: var(--accent-fill) !important;
}

.thumbnail-area.is-missing .thumbnail-img,
.thumbnail-area.is-missing .thumbnail-placeholder {
  filter: grayscale(1);
  opacity: 0.45;
}

.missing-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 7px;
  border-radius: 6px;
  background-color: var(--overlay-badge);
  border: 1px solid var(--el-color-warning);
  color: var(--el-color-warning);
  font-size: 12px;
  font-weight: 600;
}

.episode-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background-color: var(--overlay-badge);
  color: #fff;
  font-size: 12px;
  padding: 2px 7px;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}

.resume-bar {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  background: var(--accent-fill);
  border-radius: 0 2px 2px 0;
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 2px;
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
  color: var(--text-glass-secondary);
  opacity: 0.4;
}

.star-icon.filled {
  color: var(--star-filled);
  opacity: 1;
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
</style>
