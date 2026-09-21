<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import { getSettings, updateSettings, type Settings } from '@/api/settings'

// 这一页只剩系统配置（owner 可见）；主题这类个人偏好在 /profile 按人保存。
const settings = ref<Settings>({
  auto_scan_enabled: true,
  auto_scan_interval: 3600,
  default_transcode_format: 'mp4',
  thumbnail_width: 320,
  thumbnail_height: 180,
})
const loading = ref(false)
const saving = ref(false)

const transcodeFormats = [
  { label: 'MP4 (H.264)', value: 'mp4' },
  { label: 'MP4 (H.265)', value: 'mp4_h265' },
  { label: 'WebM (VP9)', value: 'webm' },
  { label: 'AVI', value: 'avi' },
  { label: 'MKV', value: 'mkv' },
]

const scanIntervals = [
  { label: '每 15 分钟', value: 900 },
  { label: '每 30 分钟', value: 1800 },
  { label: '每小时', value: 3600 },
  { label: '每 2 小时', value: 7200 },
  { label: '每 6 小时', value: 21600 },
  { label: '每天', value: 86400 },
]

async function loadSettings() {
  loading.value = true
  try {
    settings.value = await getSettings()
  } catch (err: unknown) {
    ElMessage.error(`加载设置失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await updateSettings(settings.value)
    ElMessage.success('设置已保存')
  } catch (err: unknown) {
    ElMessage.error(`保存失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div class="settings-page" v-loading="loading">
    <div class="page-header">
      <h2>
        <el-icon><Setting /></el-icon>
        应用设置
      </h2>
    </div>

    <el-card class="settings-card">
      <template #header>
        <div class="card-header">
          <span>扫描设置</span>
        </div>
      </template>

      <el-form label-width="140px" label-position="left">
        <el-form-item label="自动扫描">
          <el-switch v-model="settings.auto_scan_enabled" />
          <span class="form-hint">启用后将按照设定的间隔自动扫描视频源</span>
        </el-form-item>

        <el-form-item label="扫描间隔">
          <el-select v-model="settings.auto_scan_interval" style="width: 200px">
            <el-option
              v-for="item in scanIntervals"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card">
      <template #header>
        <div class="card-header">
          <span>转码设置</span>
        </div>
      </template>

      <el-form label-width="140px" label-position="left">
        <el-form-item label="默认转码格式">
          <el-select v-model="settings.default_transcode_format" style="width: 200px">
            <el-option
              v-for="item in transcodeFormats"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <span class="form-hint">新视频转码时的默认目标格式</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card">
      <template #header>
        <div class="card-header">
          <span>缩略图设置</span>
        </div>
      </template>

      <el-form label-width="140px" label-position="left">
        <el-form-item label="缩略图宽度">
          <el-input-number
            v-model="settings.thumbnail_width"
            :min="100"
            :max="1920"
            :step="10"
          />
          <span class="form-hint">像素</span>
        </el-form-item>

        <el-form-item label="缩略图高度">
          <el-input-number
            v-model="settings.thumbnail_height"
            :min="60"
            :max="1080"
            :step="10"
          />
          <span class="form-hint">像素</span>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="actions">
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存设置
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 4px 0;
  max-width: 800px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.settings-card {
  margin-bottom: 20px;
}

.card-header {
  font-weight: 600;
}

.form-hint {
  margin-left: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.actions {
  display: flex;
  justify-content: flex-end;
  padding: 20px 0;
}
</style>
