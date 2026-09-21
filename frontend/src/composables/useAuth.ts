import { computed, ref } from 'vue'
import * as authApi from '@/api/auth'
import { loadAccountTheme } from '@/composables/useTheme'
import type { AuthUser } from '@/types/auth'

/**
 * 全站唯一的登录态。没有 Pinia，跟 useTheme 一样用模块级 ref：
 * 路由守卫在组件之外也要能读写它。
 */
const user = ref<AuthUser | null>(null)
const needsSetup = ref(false)
const loaded = ref(false)

/** 拉取偏差不该拖住登录：主题晚一帧到位可以接受，卡在登录页不行。 */
function syncThemeFromAccount(): void {
  void loadAccountTheme().catch(() => {
    // 未登录、服务端不可达：本机继续沿用 localStorage 里的主题
  })
}

/** 读取当前会话；同一浏览器只探测一次，除非 force。 */
async function load(force = false): Promise<AuthUser | null> {
  if (loaded.value && !force) return user.value
  const status = await authApi.getAuthStatus()
  needsSetup.value = status.needs_setup
  user.value = status.authenticated ? await authApi.getMe() : null
  loaded.value = true
  if (user.value) syncThemeFromAccount()
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
  // 登录之后立刻换成这个人自己的主题：这台设备刚才显示的可能是上一个人。
  syncThemeFromAccount()
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
