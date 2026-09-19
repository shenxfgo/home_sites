<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getWatchStats } from '@/api/history'
import type { WatchStats } from '@/api/history'

const windows = [
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 90, label: '近 90 天' },
  { days: 365, label: '近一年' },
]

const activeDays = ref(30)
const stats = ref<WatchStats | null>(null)
const loading = ref(false)

const daily = computed(() => stats.value?.daily ?? [])
const maxDaySeconds = computed(() =>
  daily.value.reduce((max, entry) => Math.max(max, entry.seconds), 0)
)
const maxTagSeconds = computed(() =>
  (stats.value?.tags ?? []).reduce((max, tag) => Math.max(max, tag.seconds), 0)
)
const rangeStart = computed(() => daily.value[0]?.date ?? '')
const rangeEnd = computed(() => daily.value[daily.value.length - 1]?.date ?? '')

function barHeight(seconds: number): string {
  return `${Math.max(2, Math.round((seconds / maxDaySeconds.value) * 100))}%`
}

function tagWidth(seconds: number): string {
  return `${Math.max(2, Math.round((seconds / maxTagSeconds.value) * 100))}%`
}

/** Hours rule the page, so anything under an hour would read as 0.0. */
function formatHours(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  return `${(seconds / 3600).toFixed(1)} 小时`
}

function formatDay(iso: string): string {
  const [, month, day] = iso.split('-')
  if (!month) return ''
  return `${Number(month)}月${Number(day)}日`
}

async function load() {
  loading.value = true
  try {
    stats.value = await getWatchStats(activeDays.value)
  } catch (err: unknown) {
    ElMessage.error(`加载统计失败：${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

function pickWindow(days: number) {
  if (days === activeDays.value) return
  activeDays.value = days
  load()
}

onMounted(load)
</script>

<template>
  <div class="stats-page">
    <div class="stats-head">
      <h2 class="page-title">观影统计</h2>
      <div class="window-picker">
        <button
          v-for="entry in windows"
          :key="entry.days"
          class="window-btn"
          :class="{ active: activeDays === entry.days }"
          @click="pickWindow(entry.days)"
        >
          {{ entry.label }}
        </button>
      </div>
    </div>

    <div v-loading="loading" class="stats-body">
      <div class="stat-row">
        <div class="stat-card">
          <span class="stat-label">本月观看</span>
          <span class="stat-value">{{ formatHours(stats?.month_seconds ?? 0) }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">{{ activeDays }} 天内</span>
          <span class="stat-value">{{ formatHours(stats?.window_seconds ?? 0) }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">看过影片</span>
          <span class="stat-value">{{ stats?.videos_watched ?? 0 }} 部</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">最长连看</span>
          <span class="stat-value">{{ stats?.longest_streak_days ?? 0 }} 天</span>
          <span class="stat-note">{{ stats?.active_days ?? 0 }} 天有记录</span>
        </div>
      </div>

      <section class="panel">
        <h3 class="panel-title">每天看了多久</h3>
        <p v-if="!maxDaySeconds" class="panel-empty">
          这段时间还没有观看记录，播放任意视频后再回到这里。
        </p>
        <template v-else>
          <div class="chart">
            <div
              v-for="entry in daily"
              :key="entry.date"
              class="bar-cell"
              :title="`${formatDay(entry.date)} ${formatHours(entry.seconds)}`"
            >
              <div class="bar" :style="{ height: barHeight(entry.seconds) }"></div>
            </div>
          </div>
          <div class="chart-axis">
            <span>{{ formatDay(rangeStart) }}</span>
            <span>{{ formatDay(rangeEnd) }}</span>
          </div>
        </template>
      </section>

      <section class="panel">
        <h3 class="panel-title">时间花在了哪些标签上</h3>
        <p v-if="!stats?.tags.length" class="panel-empty">
          看过的影片还没有标签，给它们打上标签后这里就有内容了。
        </p>
        <div v-else class="tag-list">
          <div v-for="tag in stats?.tags" :key="tag.name" class="tag-row">
            <span class="tag-name">{{ tag.name }}</span>
            <span class="tag-track">
              <span
                class="tag-fill"
                :style="{ width: tagWidth(tag.seconds), background: tag.color }"
              ></span>
            </span>
            <span class="tag-seconds">{{ formatHours(tag.seconds) }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.stats-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 960px;
}

.stats-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.window-picker {
  display: flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-pill);
  background: var(--surface-bg);
}

.window-btn {
  padding: 5px 12px;
  border: none;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--text-glass-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.window-btn:hover {
  color: var(--text-glass);
}

.window-btn.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.stats-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  background: var(--glass-bg);
  box-shadow: var(--glass-shadow);
}

.stat-label {
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-glass);
}

.stat-note {
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.panel {
  padding: 18px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  background: var(--glass-bg);
}

.panel-title {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
}

.panel-empty {
  margin: 0;
  padding: 24px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.chart {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 160px;
}

.bar-cell {
  flex: 1;
  min-width: 2px;
  height: 100%;
  display: flex;
  align-items: flex-end;
}

.bar {
  width: 100%;
  border-radius: 2px 2px 0 0;
  background: var(--accent-soft);
  border-bottom: 2px solid var(--accent);
}

.bar-cell:hover .bar {
  background: var(--accent);
}

.chart-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.tag-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tag-row {
  display: grid;
  grid-template-columns: 96px 1fr 72px;
  align-items: center;
  gap: 12px;
}

.tag-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-track {
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--tile-bg);
  overflow: hidden;
}

.tag-fill {
  display: block;
  height: 100%;
  border-radius: var(--radius-pill);
}

.tag-seconds {
  font-size: 12px;
  text-align: right;
  color: var(--text-glass-secondary);
}
</style>
