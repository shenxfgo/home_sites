<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const router = useRouter()
const { signIn, needsSetup, load } = useAuth()

const username = ref('')
const password = ref('')
const remember = ref(false)
const submitting = ref(false)
const errorMessage = ref('')

// 只有站内相对路径值得跟：'//host' 会被浏览器当协议相对地址解析。
const redirectTo = computed(() => {
  const raw = route.query.redirect
  const target = Array.isArray(raw) ? raw[0] : raw
  return target && target.startsWith('/') && !target.startsWith('//') ? target : '/'
})

onMounted(() => {
  // 首启状态决定要不要给出建号指引；登录页本身是公开接口，不怕 401。
  void load().catch(() => undefined)
})

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await signIn(username.value.trim(), password.value, remember.value)
    await router.replace(redirectTo.value)
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '登录失败'
    password.value = ''
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card glass-panel">
      <h1 class="brand accent-text">Home Sites</h1>
      <p class="tagline">家庭影库，登录后可见</p>

      <p v-if="needsSetup" class="notice">
        还没有任何账号。请先在后端目录执行
        <code>uv run python -m src.cli create-user</code> 建好第一个账号。
      </p>

      <form class="fields" @submit.prevent="submit">
        <div class="field">
          <label class="field-label" for="login-username">账号</label>
          <el-input
            id="login-username"
            v-model="username"
            name="username"
            autocomplete="username"
            placeholder="小写字母、数字或 . _ -"
            :disabled="submitting"
          />
        </div>
        <div class="field">
          <label class="field-label" for="login-password">密码</label>
          <el-input
            id="login-password"
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            show-password
            placeholder="至少 8 位"
            :disabled="submitting"
          />
        </div>

        <el-checkbox v-model="remember" class="remember" :disabled="submitting">
          记住我 30 天
        </el-checkbox>

        <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>

        <el-button type="primary" native-type="submit" class="submit" :loading="submitting">
          登录
        </el-button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--page-bg);
}

.login-card {
  width: 100%;
  max-width: 380px;
  padding: 36px 36px 40px;
  border-radius: var(--radius-panel);
}

.brand {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.tagline {
  margin: 6px 0 24px;
  font-size: 13px;
  color: var(--text-glass-secondary);
}

.notice {
  margin: 0 0 20px;
  padding: 10px 12px;
  border: 1px solid var(--glass-border-strong);
  border-radius: var(--radius-tile);
  background: var(--tile-bg);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-glass-secondary);
}

.notice code {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: var(--text-glass);
}

.field + .field {
  margin-top: 14px;
}

.field-label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
  color: var(--text-glass-secondary);
}

.remember {
  margin: 12px 0 0;
}

.error {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--danger-solid);
}

.submit {
  width: 100%;
  margin-top: 8px;
}
</style>
