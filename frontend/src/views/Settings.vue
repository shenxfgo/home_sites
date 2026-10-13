<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import { getSettings, updateSettings, type Settings } from '@/api/settings'

// 这一页只剩系统配置（owner 可见）；主题这类个人偏好在 /profile 按人保存。
//
// 读回来之前这一页**一个数也不揣**（#214，面板 ⑦ 甲）：从前这五个初始字面量
// （true / 3600 / 'mp4' / 320 / 180）只在 `GET /api/settings` 失败那一格露出来，
// 显示的却是界面自己替服务器做的决定。而 `PUT /api/settings` 的请求模型五个键
// 全都带默认值——漏一格不是那格不动，是把它写回代码默认值，所以"半张表"连保存
// 的资格都没有（`canSave` 就是这道闸）。
type SettingsDraft = Partial<Settings>

const settings = ref<SettingsDraft>({})
const loading = ref(false)
const saving = ref(false)

/** 五格都读回来过，才谈得上整表写回去。 */
function isComplete(draft: SettingsDraft): draft is Settings {
  return (
    draft.auto_scan_enabled !== undefined &&
    draft.auto_scan_interval !== undefined &&
    draft.default_transcode_format !== undefined &&
    draft.thumbnail_width !== undefined &&
    draft.thumbnail_height !== undefined
  )
}

const canSave = computed(() => isComplete(settings.value))

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
  // 按钮在未读全时就是按不动的（模板那道 `:disabled`），这一句要的是类型收窄：
  // 过了它，`settings.value` 才真的是一份全五项的 `Settings`。
  const draft = settings.value
  if (!isComplete(draft)) return

  saving.value = true
  try {
    await updateSettings(draft)
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
          <!-- 占位文案必须自己写：全站没给 Element Plus 配中文 locale，空值时组件默认显示英文
               "Select"，而 #214 之后空值是这个页面开局的第一态。 -->
          <el-select v-model="settings.auto_scan_interval" placeholder="未读取" style="width: 200px">
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
          <el-select v-model="settings.default_transcode_format" placeholder="未读取" style="width: 200px">
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
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!canSave"
        @click="handleSave"
      >
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
