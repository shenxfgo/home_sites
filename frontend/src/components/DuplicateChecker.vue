<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { deleteVideo, listDuplicates } from '@/api/videos'
import type { DuplicateGroup, Video } from '@/types/video'

const groups = ref<DuplicateGroup[]>([])
const checking = ref(false)
const hasChecked = ref(false)
/** Video id currently being removed, so only its own button spins. */
const removingId = ref<number | null>(null)

const extraCopies = computed(() =>
  groups.value.reduce((sum, group) => sum + group.items.length - 1, 0),
)
const reclaimable = computed(() =>
  groups.value.reduce(
    (sum, group) => sum + group.file_size * (group.items.length - 1),
    0,
  ),
)

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '未知时长'
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} 分钟`
  return `${Math.floor(mins / 60)} 小时 ${mins % 60} 分`
}

async function check() {
  checking.value = true
  try {
    groups.value = await listDuplicates()
    hasChecked.value = true
  } catch (err: unknown) {
    ElMessage.error(`检测失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    checking.value = false
  }
}

/** Drop removed rows from the report, keeping only groups still worth showing. */
function applyRemoval(ids: number[]) {
  const gone = new Set(ids)
  groups.value = groups.value
    .map((group) => {
      const items = group.items.filter((item) => !gone.has(item.id))
      return {
        ...group,
        items,
        count: items.length,
        keep_id: items.some((item) => item.id === group.keep_id)
          ? group.keep_id
          : items[0]?.id ?? 0,
      }
    })
    .filter((group) => group.items.length > 1)
}

async function removeOne(video: Video) {
  const ok = await confirmRemoval(1)
  if (!ok) return
  removingId.value = video.id
  try {
    await deleteVideo(video.id)
    applyRemoval([video.id])
    ElMessage.success('已移除这条记录')
  } catch (err: unknown) {
    ElMessage.error(`移除失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    removingId.value = null
  }
}

async function removeExtras(group: DuplicateGroup) {
  const extras = group.items.filter((item) => item.id !== group.keep_id)
  if (!extras.length) return
  const ok = await confirmRemoval(extras.length)
  if (!ok) return
  try {
    await Promise.all(extras.map((item) => deleteVideo(item.id)))
    applyRemoval(extras.map((item) => item.id))
    ElMessage.success(`已移除 ${extras.length} 条重复记录`)
  } catch (err: unknown) {
    ElMessage.error(`移除失败: ${err instanceof Error ? err.message : err}`)
  }
}

async function confirmRemoval(count: number): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      `将从库里移除 ${count} 条记录。磁盘上的文件不会被动，请到文件管理器里删掉它，否则下次扫描会重新收录。`,
      '确认移除记录',
      { confirmButtonText: '移除记录', cancelButtonText: '再想想', type: 'warning' },
    )
    return true
  } catch {
    return false
  }
}
</script>

<template>
  <el-card shadow="never" class="dup-card">
    <div class="dup-header">
      <div class="dup-heading">
        <h3>重复文件检测</h3>
        <p>
          先按文件大小与时长分组，再读取文件首尾各 1MB 确认内容一致，只有完全相同的文件才会列出来。
        </p>
      </div>
      <el-button type="primary" plain :loading="checking" :icon="Refresh" @click="check">
        {{ hasChecked ? '重新检测' : '开始检测' }}
      </el-button>
    </div>

    <div v-if="hasChecked && !checking && groups.length === 0" class="dup-empty">
      没有发现内容完全相同的文件。
    </div>

    <div v-if="groups.length" class="dup-summary">
      <span>{{ groups.length }} 组重复，多占 {{ extraCopies }} 份 · 可回收 {{ formatSize(reclaimable) }}</span>
    </div>

    <section
      v-for="group in groups"
      :key="group.items.map((item) => item.id).join('-')"
      class="dup-group"
    >
      <header class="dup-group-head">
        <div class="dup-group-meta">
          <strong>{{ group.items.length }} 份相同的文件</strong>
          <span>每份 {{ formatSize(group.file_size) }} · {{ formatDuration(group.duration) }} · 多占 {{ formatSize(group.file_size * (group.items.length - 1)) }}</span>
        </div>
        <el-button
          size="small"
          type="danger"
          plain
          @click="removeExtras(group)"
        >
          移除多余记录
        </el-button>
      </header>

      <ul class="dup-items">
        <li v-for="item in group.items" :key="item.id" class="dup-item">
          <el-tag v-if="item.id === group.keep_id" type="success" size="small" class="keep-tag">
            建议保留
          </el-tag>
          <div class="dup-item-meta">
            <span class="dup-title">{{ item.title || item.filepath }}</span>
            <span class="dup-path" :title="item.filepath">{{ item.filepath }}</span>
            <span class="dup-stats">
              看过 {{ item.view_count }} 次
              <template v-if="item.progress"> · 进度 {{ formatDuration(item.progress) }}</template>
              <template v-if="item.is_missing"> · 文件已丢失</template>
            </span>
          </div>
          <el-button
            text
            type="danger"
            :loading="removingId === item.id"
            @click="removeOne(item)"
          >
            移除记录
          </el-button>
        </li>
      </ul>
    </section>
  </el-card>
</template>

<style scoped>
.dup-card {
  margin-top: 28px;
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: var(--radius-panel) !important;
}

.dup-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.dup-heading h3 {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-glass);
}

.dup-heading p {
  margin: 0;
  max-width: 640px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-glass-secondary);
}

.dup-empty,
.dup-summary {
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.dup-summary {
  padding-top: 14px;
  border-top: 1px solid var(--glass-border);
}

.dup-group {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-tile);
  background: var(--tile-bg);
}

.dup-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.dup-group-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--text-glass);
}

.dup-group-meta span {
  color: var(--text-glass-secondary);
}

.dup-items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.dup-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--glass-border);
}

.keep-tag {
  flex: none;
}

.dup-item-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.dup-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-glass);
}

.dup-path {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--text-glass-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dup-stats {
  font-size: 12px;
  color: var(--text-glass-secondary);
}
</style>
