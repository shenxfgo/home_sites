<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword, listSessions, revokeSession } from '@/api/auth'
import { getTheme, setTheme, type Theme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'
import type { AuthDevice } from '@/types/auth'

const { user } = useAuth()

const themes: { label: string; value: Theme }[] = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
  { label: '跟随系统', value: 'auto' },
]

// 选中即保存：主题这一格没有"保存"按钮，切了就该生效。
const theme = ref<Theme>(getTheme())
const chosenRole = computed(() => (user.value?.role === 'owner' ? '管理员' : '成员'))

function applyTheme(value: Theme) {
  theme.value = value
  setTheme(value)
}

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const saving = ref(false)

async function handleChangePassword() {
  if (saving.value) return
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  if (newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  saving.value = true
  try {
    await changePassword(oldPassword.value, newPassword.value)
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    ElMessage.success('密码已更新，其他设备需要用它重新登录')
    // 服务端顺手退了别的浏览器，本地那几行就成了假数据：重读而不是本地删。
    await loadDevices()
  } catch (err: unknown) {
    ElMessage.error(`修改失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    saving.value = false
  }
}

const devices = ref<AuthDevice[]>([])
const devicesLoading = ref(false)
const revoking = ref<string | null>(null)

// User-Agent 只拿来决定这一行显示什么，任何判断都不看它：那句话是客户端自己写的。
const BROWSER_LABELS: [RegExp, string][] = [
  [/Edg\//, 'Edge'],
  [/OPR\//, 'Opera'],
  [/Firefox\//, 'Firefox'],
  // Edge 与 Opera 的字符串里也带 Chrome，所以必须排在它们后面。
  [/Chrome\//, 'Chrome'],
  [/Safari\//, 'Safari'],
]
const SYSTEM_LABELS: [RegExp, string][] = [
  [/iPhone|iPad|iPod/, 'iOS'],
  [/Android/, 'Android'],
  [/Windows/, 'Windows'],
  [/Mac OS X/, 'macOS'],
  [/Linux/, 'Linux'],
]

function deviceLabel(userAgent: string | null): string {
  if (!userAgent) return '未知设备'
  const browser = BROWSER_LABELS.find(([pattern]) => pattern.test(userAgent))?.[1]
  const system = SYSTEM_LABELS.find(([pattern]) => pattern.test(userAgent))?.[1]
  if (browser || system) return [browser, system].filter(Boolean).join(' · ')
  // 认不出来也要留个能核对的痕迹，比一行"未知设备"有用。
  return userAgent.slice(0, 40)
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

async function loadDevices() {
  devicesLoading.value = true
  try {
    devices.value = await listSessions()
  } catch (err: unknown) {
    ElMessage.error(`读取登录设备失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    devicesLoading.value = false
  }
}

async function handleRevoke(device: AuthDevice) {
  if (revoking.value) return
  revoking.value = device.token_hash
  try {
    await revokeSession(device.token_hash)
    devices.value = devices.value.filter((row) => row.token_hash !== device.token_hash)
    ElMessage.success('该设备已退出，下次要用密码重新登录')
  } catch (err: unknown) {
    ElMessage.error(`退出失败: ${err instanceof Error ? err.message : err}`)
    await loadDevices()
  } finally {
    revoking.value = null
  }
}

onMounted(loadDevices)
</script>

<template>
  <div class="profile-page">
    <div class="page-header">
      <h2>个人设置</h2>
    </div>

    <el-card class="profile-card card-account">
      <template #header><span>账号</span></template>
      <el-form label-width="120px" label-position="left">
        <el-form-item label="登录账号">
          <span class="value">{{ user?.username ?? '—' }}</span>
        </el-form-item>
        <el-form-item label="昵称">
          <span class="value">{{ user?.display_name || '未设置' }}</span>
        </el-form-item>
        <el-form-item label="角色">
          <span class="value">{{ chosenRole }}</span>
          <span class="form-hint">角色由管理员在「用户管理」里调整</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="profile-card card-theme">
      <template #header><span>界面</span></template>
      <el-form label-width="120px" label-position="left">
        <el-form-item label="主题">
          <el-radio-group :model-value="theme" @change="applyTheme($event as Theme)">
            <el-radio v-for="item in themes" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
          <span class="form-hint">只跟着你这个账号，换台设备登录还是这个样子</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="profile-card card-password">
      <template #header><span>修改密码</span></template>
      <el-form label-width="120px" label-position="left">
        <el-form-item label="当前密码">
          <el-input
            v-model="oldPassword"
            type="password"
            show-password
            autocomplete="current-password"
            class="field"
          />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="newPassword"
            type="password"
            show-password
            autocomplete="new-password"
            placeholder="至少 8 位"
            class="field"
          />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input
            v-model="confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            class="field"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleChangePassword">
            更新密码
          </el-button>
          <span class="form-hint">改完后其他浏览器会被退出，这台仍然保持登录</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="devicesLoading && !devices.length" class="profile-card card-devices">
      <template #header>
        <div class="card-header">
          <span>登录设备</span>
          <el-button size="small" text :loading="devicesLoading" @click="loadDevices">
            刷新
          </el-button>
        </div>
      </template>
      <el-empty v-if="!devices.length && !devicesLoading" description="没有查到有效会话" :image-size="60" />
      <ul v-else class="device-list">
        <li v-for="device in devices" :key="device.token_hash" class="device-item">
          <div class="device-main">
            <span class="device-name">{{ deviceLabel(device.user_agent) }}</span>
            <el-tag v-if="device.current" size="small" type="success">当前设备</el-tag>
          </div>
          <div class="device-meta">
            <span>最近活动 {{ formatDate(device.last_seen_at) }}</span>
            <span>有效期至 {{ formatDate(device.expires_at) }}</span>
          </div>
          <el-button
            v-if="!device.current"
            size="small"
            type="warning"
            plain
            :loading="revoking === device.token_hash"
            @click="handleRevoke(device)"
          >
            退出
          </el-button>
          <span v-else class="device-hint">顶栏的「退出登录」管这一台</span>
        </li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped>
.profile-page {
  padding: 4px 0;
  max-width: 720px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.profile-card {
  margin-bottom: 20px;
}

.value {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.field {
  max-width: 280px;
}

.form-hint {
  margin-left: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.device-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.device-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.device-item:last-child {
  border-bottom: none;
}

.device-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 180px;
}

.device-name {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.device-meta {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.device-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
