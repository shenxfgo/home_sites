import { computed, ref } from 'vue'
import * as authApi from '@/api/auth'
import type { AuthUser } from '@/types/auth'

/**
 * 全站唯一的登录态。没有 Pinia，跟 useTheme 一样用模块级 ref：
 * 路由守卫在组件之外也要能读写它。
 */
const user = ref<AuthUser | null>(null)
const needsSetup = ref(false)
const loaded = ref(false)

/** 读取当前会话；同一浏览器只探测一次，除非 force。 */
async function load(force = false): Promise<AuthUser | null> {
  if (loaded.value && !force) return user.value
  const status = await authApi.getAuthStatus()
  needsSetup.value = status.needs_setup
  user.value = status.authenticated ? await authApi.getMe() : null
  loaded.value = true
  return user.value
}

/** 后端回了 401：本地状态立刻作废，下一次导航会重新探测。 */
function forget(): void {
  user.value = null
  loaded.value = false
}

async function signIn(
  username: string,
  password: string,
  remember = false,
): Promise<AuthUser> {
  user.value = await authApi.login(username, password, remember)
  needsSetup.value = false
  loaded.value = true
  return user.value
}

async function signOut(): Promise<void> {
  await authApi.logout()
  forget()
  needsSetup.value = false
}

export function useAuth() {
  return {
    user: computed(() => user.value),
    isAuthenticated: computed(() => user.value !== null),
    isOwner: computed(() => user.value?.role === 'owner'),
    needsSetup: computed(() => needsSetup.value),
    loaded: computed(() => loaded.value),
    load,
    forget,
    signIn,
    signOut,
  }
}
