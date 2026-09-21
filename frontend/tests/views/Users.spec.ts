import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox, ElSelect, ElSwitch } from 'element-plus'
import Users from '@/views/Users.vue'
import {
  createUser,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  setUserRole,
  setUserStatus,
} from '@/api/users'
import type { AdminUser } from '@/types/auth'
import { CONFIRMED } from '../helpers'

// 这一页只关心界面上的护栏：谁能被停用、报错怎么回到人眼里。
vi.mock('@/api/users', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  setUserRole: vi.fn(),
  setUserStatus: vi.fn(),
  resetUserPassword: vi.fn(),
  revokeUserSessions: vi.fn(),
}))

// 只有"我是谁"这一件事需要登录态：本人那一行的停用开关要关掉。
const currentUser = vi.hoisted(() => ({ value: { id: 1, username: 'tester', role: 'owner' } }))
vi.mock('@/composables/useAuth', () => ({
  useAuth: () => ({ user: currentUser }),
}))

/** The dialog's 创建 button. */
function submitIn(wrapper: VueWrapper) {
  const found = wrapper
    .get('.el-dialog')
    .findAll('button')
    .find((node) => node.text().includes('创建'))
  if (!found) throw new Error('对话框里没有创建按钮')
  return found
}

const SELF: AdminUser = {
  id: 1,
  username: 'tester',
  role: 'owner',
  display_name: 'Tester',
  is_active: true,
  created_at: '2026-09-20T08:00:00',
  last_login_at: '2026-09-20T09:00:00',
  signed_in_devices: 2,
}
const KID: AdminUser = {
  id: 2,
  username: 'kid',
  role: 'member',
  display_name: null,
  is_active: true,
  created_at: null,
  last_login_at: null,
  signed_in_devices: 0,
}

// attachTo 是必须的：el-dialog 默认就地渲染，不开在 body 上就查不到。
async function mountUsers(rows: AdminUser[] = [SELF, KID]) {
  vi.mocked(listUsers).mockResolvedValue(rows)
  const wrapper = mount(Users, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('Users view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser.value = { id: 1, username: 'tester', role: 'owner' }
    vi.mocked(setUserRole).mockResolvedValue(KID)
    vi.mocked(setUserStatus).mockResolvedValue(KID)
    vi.mocked(createUser).mockResolvedValue(KID)
    vi.mocked(resetUserPassword).mockResolvedValue(undefined)
    vi.mocked(revokeUserSessions).mockResolvedValue(2)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: 'newer-pass', action: 'confirm' } as never)
  })

  it('lists every account with its role and open browsers', async () => {
    const wrapper = await mountUsers()

    expect(listUsers).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('tester')
    expect(wrapper.text()).toContain('kid')
    expect(wrapper.text()).toContain('Tester')
    // 设备数是要看的：0 个设备就不必给"踢下线"。
    expect(wrapper.text()).toContain('2')
    expect(wrapper.find('.cell-self').text()).toBe('本人')
    wrapper.unmount()
  })

  it('will not let the owner disable their own account', async () => {
    const wrapper = await mountUsers()

    const switches = wrapper.findAllComponents(ElSwitch)
    expect(switches[0].props('disabled')).toBe(true)
    expect(switches[1].props('disabled')).toBe(false)

    await switches[1].vm.$emit('change', false)
    await flushPromises()

    expect(setUserStatus).toHaveBeenCalledWith(2, false)
    wrapper.unmount()
  })

  it('sends a role change and reloads the table', async () => {
    const wrapper = await mountUsers()

    await wrapper.findAllComponents(ElSelect)[1].vm.$emit('change', 'owner')
    await flushPromises()

    expect(setUserRole).toHaveBeenCalledWith(2, 'owner')
    expect(listUsers).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows the server reason when the last owner would be lost', async () => {
    const wrapper = await mountUsers()
    vi.mocked(setUserRole).mockRejectedValue(new Error('至少要保留一个可用的管理员，不能降级最后一个'))

    await wrapper.findAllComponents(ElSelect)[1].vm.$emit('change', 'member')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('不能降级最后一个'))
    // 本地那行被下拉框改过了，必须重载回服务端的真相
    expect(listUsers).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('creates an account with a trimmed name and no empty nickname', async () => {
    const wrapper = await mountUsers()

    await wrapper.get('.page-header button').trigger('click')
    await flushPromises()
    const fields = wrapper.get('.el-dialog').findAll('input')
    await fields[0].setValue('  小明  ')
    await fields[1].setValue('secret-pass')
    await submitIn(wrapper).trigger('click')
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith({
      username: '小明',
      password: 'secret-pass',
      role: 'member',
      display_name: null,
    })
    expect(listUsers).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('refuses to create an account without a password', async () => {
    const wrapper = await mountUsers()

    await wrapper.get('.page-header button').trigger('click')
    await flushPromises()
    await submitIn(wrapper).trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalled()
    expect(createUser).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('resets a password and signs that account out everywhere', async () => {
    const wrapper = await mountUsers()

    const reset = wrapper.findAll('button').filter((node) => node.text().includes('重置密码'))[1]
    await reset?.trigger('click')
    await flushPromises()

    expect(ElMessageBox.prompt).toHaveBeenCalled()
    expect(resetUserPassword).toHaveBeenCalledWith(2, 'newer-pass')
    wrapper.unmount()
  })

  it('only offers 踢下线 where a browser is actually open', async () => {
    const wrapper = await mountUsers()

    const kicks = wrapper.findAll('button').filter((node) => node.text().includes('踢下线'))
    // 第一行是本人（开着 2 个设备），第二行一个设备都没有
    expect(kicks[0].attributes('disabled')).toBeUndefined()
    expect(kicks[1].attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
