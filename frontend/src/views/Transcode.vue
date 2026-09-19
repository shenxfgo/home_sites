<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'
import api from '@/api/client'

interface FormatInfo {
  format: string
  codec: string
  extension: string
}

interface Video {
  id: number
  title: string | null
  filepath: string
  format: string | null
  duration: number | null
}

interface TranscodeStatus {
  video_id: number
  is_transcoding: boolean
  status: string
  progress: number
  target_format: string | null
  output_path: string | null
  error: string | null
}

const route = useRoute()
const router = useRouter()
const videoId = ref(Number(route.params.id))

const video = ref<Video | null>(null)
const formats = ref<FormatInfo[]>([])
const selectedFormat = ref('')
const transcodeStatus = ref<TranscodeStatus | null>(null)
const transcoding = ref(false)

const filename = computed(
  () => video.value?.filepath.split(/[/\\]/).pop() ?? '',
)

const statusLabels: Record<string, string> = {
  idle: '空闲',
  running: '转码中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const statusLabel = computed(
  () => statusLabels[transcodeStatus.value?.status ?? 'idle'] ?? transcodeStatus.value?.status,
)

const statusTagType = computed(() => {
  switch (transcodeStatus.value?.status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'running':
      return 'warning'
    default:
      return 'info'
  }
})

const fetchVideo = async () => {
  try {
    const response = await api.get(`/videos/${videoId.value}`)
    video.value = response.data
  } catch (error) {
    ElMessage.error('获取视频信息失败')
    router.push('/')
  }
}

const fetchFormats = async () => {
  try {
    const response = await api.get('/transcode/formats')
    formats.value = response.data
  } catch (error) {
    console.error('获取格式列表失败:', error)
  }
}

const fetchStatus = async () => {
  try {
    const response = await api.get(`/transcode/${videoId.value}/status`)
    transcodeStatus.value = response.data
    if (transcodeStatus.value?.status === 'completed' && pollTimer) {
      ElMessage.success('转码完成')
    }
    if (transcodeStatus.value?.status === 'failed' && pollTimer) {
      ElMessage.error(transcodeStatus.value.error ?? '转码失败')
    }
  } catch (error) {
    console.error('获取转码状态失败:', error)
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await fetchStatus()
    if (!transcodeStatus.value?.is_transcoding) {
      stopPolling()
    }
  }, 1500)
}

const startTranscode = async () => {
  if (!selectedFormat.value) {
    ElMessage.warning('请选择目标格式')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要将视频转码为 ${selectedFormat.value} 格式吗？`,
      '确认转码',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )

    transcoding.value = true
    await api.post(`/transcode/${videoId.value}`, {
      target_format: selectedFormat.value
    })

    ElMessage.success('转码任务已启动')
    await fetchStatus()
    startPolling()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '转码失败')
    }
  } finally {
    transcoding.value = false
  }
}

const cancelTranscode = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要取消当前转码任务吗？',
      '取消转码',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )

    await api.post(`/transcode/${videoId.value}/cancel`)
    ElMessage.success('转码已取消')
    stopPolling()
    await fetchStatus()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '取消失败')
    }
  }
}

const formatDuration = (seconds: number | null) => {
  if (!seconds) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

watch(
  () => route.params.id,
  (id) => {
    if (id == null) return
    stopPolling()
    videoId.value = Number(id)
    transcodeStatus.value = null
    loadAll()
  }
)

const loadAll = async () => {
  await Promise.all([fetchVideo(), fetchFormats(), fetchStatus()])
  if (transcodeStatus.value?.is_transcoding) {
    startPolling()
  }
}

onMounted(loadAll)
onUnmounted(stopPolling)
</script>

<template>
  <div class="transcode-page">
    <el-page-header @back="router.back()" title="返回">
      <template #content>
        <span class="page-title">视频转码</span>
      </template>
    </el-page-header>

    <div v-if="video" class="content-card">
      <el-descriptions title="视频信息" :column="2" border>
        <el-descriptions-item label="视频标题">{{ video.title || filename }}</el-descriptions-item>
        <el-descriptions-item label="文件名">{{ filename }}</el-descriptions-item>
        <el-descriptions-item label="当前格式">{{ video.format?.toUpperCase() }}</el-descriptions-item>
        <el-descriptions-item label="时长">{{ formatDuration(video.duration) }}</el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <div class="transcode-section">
        <h3>转码设置</h3>

        <el-form label-width="100px">
          <el-form-item label="目标格式">
            <el-select v-model="selectedFormat" placeholder="选择目标格式" style="width: 300px">
              <el-option
                v-for="fmt in formats"
                :key="fmt.format"
                :label="`${fmt.format} (${fmt.extension})`"
                :value="fmt.format"
              />
            </el-select>
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              :icon="VideoPlay"
              :loading="transcoding"
              :disabled="transcodeStatus?.is_transcoding"
              @click="startTranscode"
            >
              开始转码
            </el-button>

            <el-button
              v-if="transcodeStatus?.is_transcoding"
              type="danger"
              @click="cancelTranscode"
            >
              取消转码
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <el-divider />

      <div class="status-section">
        <h3>转码状态</h3>

        <el-descriptions :column="1" border>
          <el-descriptions-item label="是否正在转码">
            <el-tag :type="transcodeStatus?.is_transcoding ? 'warning' : 'info'">
              {{ transcodeStatus?.is_transcoding ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="statusTagType">
              {{ statusLabel || '未知' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="transcodeStatus?.target_format" label="目标格式">
            {{ transcodeStatus.target_format.toUpperCase() }}
          </el-descriptions-item>
          <el-descriptions-item v-if="transcodeStatus?.is_transcoding" label="进度">
            <el-progress
              :percentage="Math.round(transcodeStatus?.progress ?? 0)"
              :stroke-width="14"
              striped
              striped-flow
              style="width: 320px"
            />
          </el-descriptions-item>
          <el-descriptions-item v-if="transcodeStatus?.error" label="失败原因">
            <span class="status-error">{{ transcodeStatus.error }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <el-divider />

      <div class="formats-section">
        <h3>支持的格式</h3>

        <el-table :data="formats" style="width: 100%">
          <el-table-column prop="format" label="格式名称" />
          <el-table-column prop="codec" label="编码器" />
          <el-table-column prop="extension" label="文件扩展名" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.transcode-page {
  padding: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-glass);
}

.content-card {
  margin-top: 20px;
  padding: 24px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  box-shadow: var(--glass-shadow);
}

.transcode-section,
.status-section,
.formats-section {
  margin-top: 20px;
}

.transcode-section h3,
.status-section h3,
.formats-section h3 {
  margin-bottom: 15px;
  color: var(--text-glass);
}

.status-error {
  color: var(--el-color-danger);
  word-break: break-all;
}
</style>
