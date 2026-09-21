import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElInput, ElMessage, ElRadioGroup } from 'element-plus'
import Profile from '@/views/Profile.vue'
import { changePassword, listSessions, revokeSession } from '@/api/auth'
import { getPreferences, updatePreferences } from '@/api/preferences'
import { getTheme } from '@/composables/useTheme'
import type { AuthDevice, AuthUser } from '@/types/auth'

vi.mock('@/api/auth', () => ({
  changePassword: vi.fn(),
  listSessions: vi.fn(),
  revokeSession: vi.fn(),
}))

// 主题走的是真正的 useTheme，这里只挡住它写回服务端的请求。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
}))

const currentUser = vi.hoisted(() => ({ value: null as AuthUser | null }))
vi.mock('@/composables/useAuth', async () => {
  const { computed } = await import('vue')
  return { useAuth: () => ({ user: computed(() => currentUser.value) }) }
})

const OWNER: AuthUser = { id: 1, username: 'tester', role: 'owner', display_name: 'Tester' }

const WHEN = '2026-09-21T02:00:00'

function device(tokenHash: string, userAgent: string | null, current = false): AuthDevice {
  return {
    token_hash: tokenHash,
    current,
    user_agent: userAgent,
    created_at: WHEN,
    last_seen_at: WHEN,
    expires_at: WHEN,
  }
}

const LAPTOP = device(
  'a'.repeat(64),
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  true,
)
const PHONE = device(
  'b'.repeat(64),
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
)

async function mountProfile() {
  const wrapper = mount(Profile)
  await flushPromises()
  return wrapper
}

describe('Profile view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser.value = OWNER
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'light' })
    vi.mocked(updatePreferences).mockResolvedValue({ theme: 'dark' })
    vi.mocked(changePassword).mockResolvedValue(undefined)
    vi.mocked(listSessions).mockResolvedValue([])
    vi.mocked(revokeSession).mockResolvedValue(undefined)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  })

  it('shows who is signed in and that the role is not theirs to change', async () => {
    const wrapper = await mountProfile()

    expect(wrapper.text()).toContain('tester')
    expect(wrapper.text()).toContain('Tester')
    expect(wrapper.text()).toContain('管理员')
    expect(wrapper.text()).toContain('用户管理')
    wrapper.unmount()
  })

  it('saves the theme on the account and applies it right away', async () => {
    const wrapper = await mountProfile()

    await wrapper.findAllComponents(ElRadioGroup)[0].vm.$emit('change', 'dark')
    await flushPromises()

    expect(updatePreferences).toHaveBeenCalledWith({ theme: 'dark' })
    expect(getTheme()).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    wrapper.unmount()
  })

  it('keeps a member\'s choice as their own', async () => {
    const wrapper = await mountProfile()

    await wrapper.findAllComponents(ElRadioGroup)[0].vm.$emit('change', 'auto')
    await flushPromises()

    // 写的是 /api/preferences（每个人一行），不是全局的 /api/settings
    expect(updatePreferences).toHaveBeenCalledWith({ theme: 'auto' })
    wrapper.unmount()
  })

  it('refuses to send mismatched passwords', async () => {
    const wrapper = await mountProfile()
    const fields = wrapper.findAllComponents(ElInput)

    await fields[0].find('input').setValue('secret-pass')
    await fields[1].find('input').setValue('newer-pass')
    await fields[2].find('input').setValue('typed-it-again')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('不一致'))
    expect(changePassword).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('refuses a new password the backend would reject', async () => {
    const wrapper = await mountProfile()
    const fields = wrapper.findAllComponents(ElInput)

    await fields[1].find('input').setValue('abc')
    await fields[2].find('input').setValue('abc')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('8 位'))
    expect(changePassword).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('rotates the password and clears the fields', async () => {
    const wrapper = await mountProfile()
    const fields = wrapper.findAllComponents(ElInput)

    await fields[0].find('input').setValue('secret-pass')
    await fields[1].find('input').setValue('newer-pass')
    await fields[2].find('input').setValue('newer-pass')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    expect(changePassword).toHaveBeenCalledWith('secret-pass', 'newer-pass')
    expect(fields[0].find('input').element.value).toBe('')
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('其他设备'))
    wrapper.unmount()
  })

  it('surfaces the reason the server said no', async () => {
    vi.mocked(changePassword).mockRejectedValue(new Error('原密码不正确'))
    const wrapper = await mountProfile()
    const fields = wrapper.findAllComponents(ElInput)

    await fields[0].find('input').setValue('wrong-one')
    await fields[1].find('input').setValue('newer-pass')
    await fields[2].find('input').setValue('newer-pass')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('原密码不正确'))
    expect(fields[0].find('input').element.value).toBe('wrong-one')
    wrapper.unmount()
  })
})

describe('Profile 登录设备', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser.value = OWNER
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'light' })
    vi.mocked(updatePreferences).mockResolvedValue({ theme: 'dark' })
    vi.mocked(changePassword).mockResolvedValue(undefined)
    vi.mocked(listSessions).mockResolvedValue([])
    vi.mocked(revokeSession).mockResolvedValue(undefined)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('reads the device list on open and names each browser', async () => {
    vi.mocked(listSessions).mockResolvedValue([LAPTOP, PHONE])
    const wrapper = await mountProfile()

    expect(listSessions).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Chrome · Windows')
    expect(wrapper.text()).toContain('Safari · iOS')
    expect(wrapper.text()).toContain('当前设备')
    wrapper.unmount()
  })

  it('leaves the device in use without an exit button', async () => {
    vi.mocked(listSessions).mockResolvedValue([LAPTOP, PHONE])
    const wrapper = await mountProfile()

    const exitButtons = wrapper.findAll('button').filter((button) => button.text() === '退出')
    expect(exitButtons).toHaveLength(1)
    wrapper.unmount()
  })

  it('drops only the device it revoked', async () => {
    vi.mocked(listSessions).mockResolvedValue([LAPTOP, PHONE])
    const wrapper = await mountProfile()
    const exitButton = wrapper.findAll('button').find((button) => button.text() === '退出')

    await exitButton?.trigger('click')
    await flushPromises()

    expect(revokeSession).toHaveBeenCalledWith(PHONE.token_hash)
    expect(wrapper.text()).toContain('Chrome · Windows')
    expect(wrapper.text()).not.toContain('Safari · iOS')
    // 本地那一行删掉就够了，成功路径不必再问一次服务端。
    expect(listSessions).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('re-reads the list when a revoke comes back denied', async () => {
    vi.mocked(listSessions).mockResolvedValue([LAPTOP, PHONE])
    vi.mocked(revokeSession).mockRejectedValue(new Error('设备不存在或已退出'))
    const wrapper = await mountProfile()
    const exitButton = wrapper.findAll('button').find((button) => button.text() === '退出')

    await exitButton?.trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('设备不存在或已退出'))
    expect(listSessions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows something to check against for a user-agent it cannot name', async () => {
    vi.mocked(listSessions).mockResolvedValue([
      device('c'.repeat(64), null, true),
      device('d'.repeat(64), 'CastB rig-07'),
    ])
    const wrapper = await mountProfile()

    expect(wrapper.text()).toContain('未知设备')
    expect(wrapper.text()).toContain('CastB rig-07')
    wrapper.unmount()
  })

  it('re-reads the list after a password change, because the server signed the others out', async () => {
    const wrapper = await mountProfile()
    const fields = wrapper.findAllComponents(ElInput)

    await fields[0].find('input').setValue('secret-pass')
    await fields[1].find('input').setValue('newer-pass')
    await fields[2].find('input').setValue('newer-pass')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()

    // 一次是进页面时读的，一次是改完密码后回来核对的。
    expect(listSessions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
