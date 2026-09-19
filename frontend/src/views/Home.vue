<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { QuestionFilled, Search, VideoCamera } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VideoCard from '@/components/VideoCard.vue'
import { listVideos, thumbnailUrl } from '@/api/videos'
import { getContinueList } from '@/api/history'
import { listSources } from '@/api/sources'
import { listTags } from '@/api/tags'
import { isTypingTarget } from '@/composables/typingGuard'
import type { Tag, Video, VideoQueryParams } from '@/types/video'
import type { Source } from '@/types/source'

const DEFAULT_PAGE_SIZE = 20
/** Query keys the URL mirrors, sorted so two serializations compare cleanly. */
const QUERY_KEYS = ['page', 'q', 'size', 'source', 'tag'] as const

// State
const videos = ref<Video[]>([])
const sources = ref<Source[]>([])
const tags = ref<Tag[]>([])
const continueVideos = ref<Video[]>([])
const loading = ref(false)
const total = ref(0)

// Filters
const search = ref('')
const selectedSourceId = ref<number | undefined>(undefined)
const selectedTagId = ref<number | undefined>(undefined)
const currentPage = ref(1)
const pageSize = ref(DEFAULT_PAGE_SIZE)
const searchInput = ref<{ focus: () => void } | null>(null)

const route = useRoute()
const router = useRouter()

const activeSearch = computed(() => search.value.trim())
const hasFilters = computed(
  () => Boolean(activeSearch.value) || selectedSourceId.value != null || selectedTagId.value != null,
)
const showResumeRail = computed(
  () => !loading.value && !hasFilters.value && continueVideos.value.length > 0,
)

/** How much of a title is still ahead of the stored position. */
function remainingOf(video: Video): number | null {
  if (video.duration == null) return null
  return Math.max(0, video.duration - (video.progress ?? 0))
}

function ratioOf(video: Video): number {
  if (!video.duration || video.progress == null) return 0
  return Math.min(1, video.progress / video.duration)
}

function titleOf(video: Video): string {
  return video.title || video.filepath.split(/[/\\]/).pop() || '无标题'
}

/** Format seconds as H:MM:SS or M:SS. */
function formatDuration(seconds: number | null): string {
  if (seconds == null) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

function openVideo(video: Video) {
  router.push({ name: 'video-detail', params: { id: video.id } })
}

/** Reduce a location query to the keys this page owns, dropping empty values. */
function normalizeQuery(query: Record<string, unknown>): string {
  const picked: Record<string, string> = {}
  for (const key of QUERY_KEYS) {
    const raw = query[key]
    const value = Array.isArray(raw) ? raw[0] : raw
    if (typeof value === 'string' && value !== '') picked[key] = value
  }
  return JSON.stringify(picked)
}

/** Current filters in the shape the URL stores them in. */
function currentQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  if (activeSearch.value) query.q = activeSearch.value
  if (selectedSourceId.value != null) query.source = String(selectedSourceId.value)
  if (selectedTagId.value != null) query.tag = String(selectedTagId.value)
  if (currentPage.value > 1) query.page = String(currentPage.value)
  if (pageSize.value !== DEFAULT_PAGE_SIZE) query.size = String(pageSize.value)
  return query
}

function firstValue(raw: unknown): string | undefined {
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && value !== '' ? value : undefined
}

function toNumber(raw: unknown): number | undefined {
  const value = firstValue(raw)
  if (value == null) return undefined
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : undefined
}

/** Read the filters out of the address bar, so a link or 后退 restores the view. */
function applyQuery() {
  const query = route.query as Record<string, unknown>
  const keyword = (firstValue(query.q) ?? '').trim()
  // Only a real change goes through the ref: the caller reloads, so the search
  // watcher must not queue a second request behind it.
  if (keyword !== search.value) {
    syncingFromUrl = true
    search.value = keyword
  }
  selectedSourceId.value = toNumber(query.source)
  selectedTagId.value = toNumber(query.tag)
  currentPage.value = Math.max(1, toNumber(query.page) ?? 1)
  const size = toNumber(query.size)
  pageSize.value = size && size >= 1 && size <= 100 ? size : DEFAULT_PAGE_SIZE
}

function pushQuery() {
  const next = currentQuery()
  if (normalizeQuery(route.query) === normalizeQuery(next)) return
  router.replace({ query: next })
}

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

async function loadContinueList() {
  try {
    continueVideos.value = await getContinueList()
  } catch {
    // Silently ignore — the rail is an extra, not a gate
  }
}

function handleSearch() {
  currentPage.value = 1
  // The keyword is a filter like any other, so it belongs in the address bar.
  pushQuery()
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
let syncingFromUrl = false
function onSearchInput() {
  if (syncingFromUrl) {
    syncingFromUrl = false
    return
  }
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(handleSearch, 400)
}

watch(search, onSearchInput)
watch([selectedSourceId, selectedTagId, currentPage, pageSize], pushQuery)

// Typing "/" jumps to the search box, the way a library site should.
function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return
  if (isTypingTarget(e.target)) return
  e.preventDefault()
  searchInput.value?.focus()
}

watch(
  () => route.query,
  (query) => {
    // Ignore the replaces this page triggered itself, and any navigation away.
    if (route.name !== 'home') return
    if (normalizeQuery(query) === normalizeQuery(currentQuery())) return
    applyQuery()
    loadVideos()
  },
)

onMounted(() => {
  applyQuery()
  loadSources()
  loadTags()
  loadContinueList()
  loadVideos()
  document.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
  if (searchTimer) clearTimeout(searchTimer)
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
        ref="searchInput"
        v-model="search"
        placeholder="搜索片名、简介或标签…（按 / 直达）"
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

    <!-- Resume rail: titles with an unfinished history row, most recent first -->
    <section v-if="showResumeRail" class="resume-rail">
      <div class="rail-head">
        <h2 class="rail-title">继续观看</h2>
        <span class="rail-count">{{ continueVideos.length }} 部没看完</span>
      </div>
      <div class="rail-row">
        <div
          v-for="video in continueVideos"
          :key="video.id"
          class="rail-item"
          @click="openVideo(video)"
        >
          <div class="rail-thumb">
            <img
              v-if="video.thumbnail_path"
              :src="thumbnailUrl(video.id)"
              :alt="titleOf(video)"
              class="rail-img"
            />
            <div v-else class="rail-placeholder">
              <el-icon :size="22"><VideoCamera /></el-icon>
            </div>
            <span class="rail-remaining">剩 {{ formatDuration(remainingOf(video)) }}</span>
            <span class="rail-bar">
              <span class="rail-bar-fill" :style="{ width: ratioOf(video) * 100 + '%' }" />
            </span>
          </div>
          <p class="rail-caption" :title="titleOf(video)">{{ titleOf(video) }}</p>
        </div>
      </div>
    </section>

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

.resume-rail {
  margin-bottom: 20px;
}

.rail-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.rail-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-glass);
}

.rail-count {
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.rail-row {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.rail-item {
  flex: 0 0 196px;
  cursor: pointer;
}

.rail-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: var(--radius-tile);
  background: var(--tile-bg);
}

.rail-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.rail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-glass-secondary);
}

.rail-remaining {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px 6px;
  border-radius: 5px;
  background-color: var(--overlay-badge);
  color: #fff;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.rail-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  background: rgba(255, 255, 255, 0.28);
}

.rail-bar-fill {
  display: block;
  height: 100%;
  background: var(--accent-fill);
}

.rail-caption {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-glass);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-item:hover .rail-caption {
  color: var(--accent);
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
