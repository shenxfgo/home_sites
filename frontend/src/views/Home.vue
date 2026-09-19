<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { QuestionFilled, Search, VideoCamera } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VideoCard from '@/components/VideoCard.vue'
import { listVideos } from '@/api/videos'
import { listSources } from '@/api/sources'
import { listTags } from '@/api/tags'
import type { Tag, Video, VideoQueryParams } from '@/types/video'
import type { Source } from '@/types/source'

// State
const videos = ref<Video[]>([])
const sources = ref<Source[]>([])
const tags = ref<Tag[]>([])
const loading = ref(false)
const total = ref(0)

// Filters
const search = ref('')
const selectedSourceId = ref<number | undefined>(undefined)
const selectedTagId = ref<number | undefined>(undefined)
const currentPage = ref(1)
const pageSize = ref(20)

const activeSearch = computed(() => search.value.trim())
const hasFilters = computed(
  () => Boolean(activeSearch.value) || selectedSourceId.value != null || selectedTagId.value != null,
)

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
    if (selectedTagId.value != null) {
      params.tag_id = selectedTagId.value
    }
    if (activeSearch.value) {
      params.search = activeSearch.value
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

async function loadTags() {
  try {
    tags.value = await listTags()
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

function handleTagChange() {
  currentPage.value = 1
  loadVideos()
}

function clearFilters() {
  search.value = ''
  selectedSourceId.value = undefined
  selectedTagId.value = undefined
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
  loadTags()
  loadVideos()
})
</script>

<template>
  <div class="home-page">
    <!-- Hero -->
    <div class="hero glass-panel">
      <h1 class="hero-title">
        你好，<span class="accent-text">放映时光</span>
      </h1>
      <p class="hero-sub">共 {{ total }} 个视频，挑一部开始今天的观影吧</p>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="搜索片名、简介或标签…"
        :prefix-icon="Search"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-select
        v-model="selectedSourceId"
        placeholder="所有视频源"
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
      <el-select
        v-model="selectedTagId"
        placeholder="所有标签"
        clearable
        filterable
        class="tag-filter"
        @change="handleTagChange"
      >
        <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
      </el-select>
      <el-popover placement="bottom-end" :width="330" trigger="click" :persistent="false">
        <template #reference>
          <el-button class="syntax-btn" :icon="QuestionFilled" circle text />
        </template>
        <div class="syntax-help">
          <p class="syntax-lead">关键词会同时搜片名、简介和标签名，多个词之间是“且”的关系。</p>
          <dl>
            <dt>暗涌 第一季</dt>
            <dd>两个词都要命中</dd>
            <dt>"dark hero"</dt>
            <dd>引号内整体匹配</dd>
            <dt>标签:悬疑</dt>
            <dd>只看标签名</dd>
            <dt>源:剧集</dt>
            <dd>限定某个视频源</dd>
            <dt>评分&gt;=4</dt>
            <dd>也可用 &gt; &lt; &lt;= =</dd>
            <dt>时长&gt;40分钟</dt>
            <dd>支持 小时/分钟/秒，省略单位按分钟</dd>
            <dt>没看过 / 未看完 / 已看完</dt>
            <dd>按播放进度筛选</dd>
          </dl>
        </div>
      </el-popover>
    </div>

    <!-- Empty state -->
    <el-empty
      v-if="!loading && videos.length === 0"
      :description="activeSearch ? '没有匹配的视频' : '没有找到视频'"
    >
      <template #image>
        <el-icon :size="64" color="var(--el-color-primary)">
          <VideoCamera />
        </el-icon>
      </template>
      <p v-if="activeSearch" class="empty-hint">
        没有与「{{ activeSearch }}」匹配的结果，换个关键词或去掉部分筛选试试。
      </p>
      <p v-else-if="hasFilters" class="empty-hint">当前筛选条件下没有视频，可以清除筛选查看全库。</p>
      <p v-else class="empty-hint">添加视频源并扫描即可开始使用。</p>
      <el-button v-if="hasFilters" class="empty-clear" @click="clearFilters">清除筛选</el-button>
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

.hero {
  padding: 26px 28px;
  margin-bottom: 16px;
  border-radius: var(--radius-panel);
  border-left: 3px solid var(--accent);
  overflow: hidden;
  position: relative;
}

.hero-title {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.2px;
  color: var(--text-glass);
}

.hero-sub {
  margin: 0;
  font-size: 14px;
  color: var(--text-glass-secondary);
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

.tag-filter {
  width: 160px;
}

.syntax-btn {
  align-self: center;
  color: var(--el-text-color-secondary);
}

.syntax-btn:hover {
  color: var(--accent);
}

.syntax-lead {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.syntax-help dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 12px;
  margin: 0;
}

.syntax-help dt {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  white-space: nowrap;
  color: var(--accent);
}

.syntax-help dd {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-hint {
  color: var(--el-text-color-secondary);
}

.empty-clear {
  margin-top: 12px;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  min-height: 200px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 24px;
  padding: 8px 0;
}
</style>
