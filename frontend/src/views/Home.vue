<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { Search, VideoCamera } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VideoCard from '@/components/VideoCard.vue'
import { listVideos } from '@/api/videos'
import { listSources } from '@/api/sources'
import type { Video, VideoQueryParams } from '@/types/video'
import type { Source } from '@/types/source'

// State
const videos = ref<Video[]>([])
const sources = ref<Source[]>([])
const loading = ref(false)
const total = ref(0)

// Filters
const search = ref('')
const selectedSourceId = ref<number | undefined>(undefined)
const currentPage = ref(1)
const pageSize = ref(20)

async function loadVideos() {
  loading.value = true
  try {
    const params: VideoQueryParams = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (selectedSourceId.value != null) {
      params.source_id = selectedSourceId.value
    }
    if (search.value.trim()) {
      params.search = search.value.trim()
    }
    const result = await listVideos(params)
    videos.value = result.items
    total.value = result.total
  } catch (err: unknown) {
    ElMessage.error(`Failed to load videos: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  try {
    sources.value = await listSources(true)
  } catch {
    // Silently ignore — filter will just be empty
  }
}

function handleSearch() {
  currentPage.value = 1
  loadVideos()
}

function handleSourceChange() {
  currentPage.value = 1
  loadVideos()
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadVideos()
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  loadVideos()
}

// Debounced search
let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(handleSearch, 400)
}

watch(search, onSearchInput)

onMounted(() => {
  loadSources()
  loadVideos()
})
</script>

<template>
  <div class="home-page">
    <!-- Toolbar -->
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="Search videos..."
        :prefix-icon="Search"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-select
        v-model="selectedSourceId"
        placeholder="All Sources"
        clearable
        class="source-filter"
        @change="handleSourceChange"
      >
        <el-option
          v-for="source in sources"
          :key="source.id"
          :label="source.name"
          :value="source.id"
        />
      </el-select>
    </div>

    <!-- Empty state -->
    <el-empty
      v-if="!loading && videos.length === 0"
      description="No videos found"
    >
      <template #image>
        <el-icon :size="64" color="var(--el-color-primary)">
          <VideoCamera />
        </el-icon>
      </template>
      <p style="color: var(--el-text-color-secondary);">
        {{ search ? 'Try adjusting your search or filters.' : 'Add a video source and scan to get started.' }}
      </p>
    </el-empty>

    <!-- Video grid -->
    <div v-loading="loading" class="video-grid">
      <VideoCard v-for="video in videos" :key="video.id" :video="video" />
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
.home-page {
  padding: 4px 0;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-input {
  max-width: 360px;
}

.source-filter {
  width: 200px;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
  min-height: 200px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding: 8px 0;
}
</style>
