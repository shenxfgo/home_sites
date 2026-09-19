<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createWatchlist,
  deleteWatchlist,
  listWatchlists,
  removeVideoFromWatchlist,
  updateWatchlist,
} from '@/api/watchlists'
import type { Watchlist } from '@/api/watchlists'
import type { Video } from '@/types/video'

const router = useRouter()

const lists = ref<Watchlist[]>([])
const loading = ref(false)

/** One dialog serves both "新建片单" and "重命名"; null id means create. */
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const formName = ref('')
const formDescription = ref('')

const totalTitles = computed(() =>
  lists.value.reduce((sum, list) => sum + list.items.length, 0)
)

/** Format seconds as H:MM:SS or M:SS. */
function formatDuration(seconds: number | null): string {
  if (seconds == null) return '未知'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function secondsOf(list: Watchlist): number {
  return list.items.reduce((sum, video) => sum + (video.duration ?? 0), 0)
}

async function load() {
  loading.value = true
  try {
    lists.value = await listWatchlists()
  } catch (err: unknown) {
    ElMessage.error(`加载片单失败：${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  formName.value = ''
  formDescription.value = ''
  formVisible.value = true
}

function openRename(list: Watchlist) {
  editingId.value = list.id
  formName.value = list.name
  formDescription.value = list.description ?? ''
  formVisible.value = true
}

async function submitForm() {
  const name = formName.value.trim()
  if (!name) {
    ElMessage.warning('片单要有个名字')
    return
  }
  try {
    if (editingId.value === null) {
      const created = await createWatchlist(name, formDescription.value.trim())
      lists.value = [...lists.value, created]
      ElMessage.success('片单已创建')
    } else {
      const updated = await updateWatchlist(editingId.value, {
        name,
        description: formDescription.value.trim(),
      })
      lists.value = lists.value.map((list) => (list.id === updated.id ? updated : list))
      ElMessage.success('片单已更新')
    }
    formVisible.value = false
  } catch (err: unknown) {
    ElMessage.error(`保存失败：${err instanceof Error ? err.message : err}`)
  }
}

async function takeOut(list: Watchlist, video: Video) {
  try {
    const updated = await removeVideoFromWatchlist(list.id, video.id)
    lists.value = lists.value.map((entry) => (entry.id === updated.id ? updated : entry))
    ElMessage.success(`已把「${video.title ?? '该影片'}」移出片单，影片仍在库里`)
  } catch (err: unknown) {
    ElMessage.error(`移出失败：${err instanceof Error ? err.message : err}`)
  }
}

async function erase(list: Watchlist) {
  try {
    await ElMessageBox.confirm(
      `将删除片单「${list.name}」及其 ${list.items.length} 条排队记录。影片本身不会被动。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteWatchlist(list.id)
    lists.value = lists.value.filter((entry) => entry.id !== list.id)
    ElMessage.success('片单已删除')
  } catch (err: unknown) {
    ElMessage.error(`删除失败：${err instanceof Error ? err.message : err}`)
  }
}

function openVideo(video: Video) {
  router.push({ name: 'video-detail', params: { id: video.id } })
}

onMounted(load)
</script>

<template>
  <div class="watchlists-page">
    <div class="page-head">
      <h2 class="page-title">片单</h2>
      <span class="page-meta">{{ lists.length }} 个片单 · {{ totalTitles }} 条排队</span>
      <el-button type="primary" @click="openCreate">新建片单</el-button>
    </div>

    <el-empty
      v-if="!loading && lists.length === 0"
      description="还没有片单。建一个，把今晚想看的几部丢进去。"
    />

    <section v-for="list in lists" :key="list.id" class="list-panel">
      <header class="list-head">
        <div class="list-heading">
          <h3 class="list-name">{{ list.name }}</h3>
          <span class="list-meta">
            {{ list.items.length }} 部 · 共 {{ formatDuration(secondsOf(list)) }}
          </span>
        </div>
        <div class="list-actions">
          <el-button text size="small" @click="openRename(list)">重命名</el-button>
          <el-button text size="small" type="danger" @click="erase(list)">删除片单</el-button>
        </div>
      </header>
      <p v-if="list.description" class="list-desc">{{ list.description }}</p>

      <p v-if="list.items.length === 0" class="queue-empty">
        这个片单还空着，去影片详情页点「加入片单」。
      </p>
      <ol v-else class="queue">
        <li v-for="(video, index) in list.items" :key="video.id" class="queue-item">
          <span class="queue-index">{{ index + 1 }}</span>
          <button class="queue-main" @click="openVideo(video)">
            <span class="queue-title">{{ video.title || video.filepath.split(/[/\\]/).pop() || '无标题' }}</span>
            <span class="queue-meta">
              {{ formatDuration(video.duration) }}
              <template v-if="video.progress != null && video.duration">
                · 已看 {{ formatDuration(video.progress) }}
              </template>
            </span>
          </button>
          <el-button text size="small" @click="takeOut(list, video)">移出</el-button>
        </li>
      </ol>
    </section>

    <el-dialog
      v-model="formVisible"
      :title="editingId === null ? '新建片单' : '重命名片单'"
      width="420px"
    >
      <el-input v-model="formName" placeholder="名字，例如 今晚看这些" maxlength="100" />
      <el-input
        v-model="formDescription"
        class="form-desc"
        type="textarea"
        :rows="2"
        placeholder="备注（可选）"
        maxlength="512"
      />
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.watchlists-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 760px;
}

.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-meta {
  flex: 1;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.list-panel {
  padding: 16px 18px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  background: var(--glass-bg);
}

.list-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.list-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.list-meta {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-glass-secondary);
}

.list-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.queue {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid var(--glass-border);
}

.queue-index {
  width: 20px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-glass-secondary);
}

.queue-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
}

.queue-title {
  font-size: 14px;
  color: var(--text-glass);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-main:hover .queue-title {
  color: var(--accent);
}

.queue-meta {
  font-size: 12px;
  color: var(--text-glass-secondary);
}

.queue-empty {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.form-desc {
  margin-top: 10px;
}
</style>
