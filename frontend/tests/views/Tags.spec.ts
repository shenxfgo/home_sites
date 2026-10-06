/**
 * 标签管理页（`views/Tags.vue`）——此前一条用例也没有。
 *
 * 浏览器那一路（`e2e/tags.spec.ts`）已经盯住了"点了按钮界面上的确有变化"，这一份管的是
 * **请求的形状**：替身夹具回的是它自己造出来的 `video_count`，所以"后端没带这个字段时界面
 * 该写什么"这种形状在 e2e 里结构上量不到；反过来"编辑没改动却发了一次 PUT"在单测里一眼可见，
 * 在浏览器里却只是"什么都没发生"。两层各挑各的钉子，不互相抄。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import Tags from '@/views/Tags.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTag, deleteTag, listTags, updateTag } from '@/api/tags'
import type { Tag } from '@/types/video'
import { makeTag } from '../factories'
import { CONFIRMED } from '../helpers'

vi.mock('@/api/tags', () => ({
  listTags: vi.fn(),
  createTag: vi.fn(),
  updateTag: vi.fn(),
  deleteTag: vi.fn(),
}))

const ACTION: Tag = { id: 1, name: '动作片', color: '#7c6cff', video_count: 2 }
const DRAMA: Tag = { id: 2, name: '文艺片', color: '#67c23a', video_count: 0 }

async function mountTags(rows: Tag[] = [ACTION]) {
  vi.mocked(listTags).mockResolvedValue(rows)
  // el-dialog 的内容要到 body 上才查得到，所以必须真的挂上去。
  const wrapper = mount(Tags, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

function dialog(wrapper: VueWrapper) {
  return wrapper.get('.el-dialog')
}

function nameField(wrapper: VueWrapper) {
  return dialog(wrapper).get('input[placeholder="请输入标签名称"]')
}

function nameValue(wrapper: VueWrapper) {
  return (nameField(wrapper).element as HTMLInputElement).value
}

/** 按文案找对话框里的按钮（创建 / 更新 / 取消）。 */
async function clickInDialog(wrapper: VueWrapper, label: string) {
  const found = dialog(wrapper)
    .findAll('button')
    .find((node) => node.text().includes(label))
  if (!found) throw new Error(`对话框里没有文案包含 "${label}" 的按钮`)
  await found.trigger('click')
  await flushPromises()
}

/** 卡片上的行内按钮（编辑 / 删除），按序号取，因为 `v-for` 渲染的顺序就是列表的顺序。 */
async function clickInCard(wrapper: VueWrapper, index: number, label: string) {
  const card = wrapper.findAll('.tag-card')[index]
  if (!card) throw new Error(`第 ${index + 1} 张标签卡片不存在`)
  const found = card.findAll('button').find((node) => node.text().includes(label))
  if (!found) throw new Error(`卡片里没有文案包含 "${label}" 的按钮`)
  await found.trigger('click')
  await flushPromises()
}

async function openCreate(wrapper: VueWrapper) {
  await wrapper.get('.page-header button').trigger('click')
  await flushPromises()
}

describe('Tags view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(createTag).mockResolvedValue(makeTag(9, '纪录片'))
    vi.mocked(updateTag).mockResolvedValue(makeTag(1, '文艺片'))
    vi.mocked(deleteTag).mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  })

  it('lists each tag with the number of videos wearing it', async () => {
    const wrapper = await mountTags([ACTION, DRAMA])

    expect(listTags).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.tag-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('动作片')
    expect(wrapper.text()).toContain('2 个视频')
    expect(wrapper.text()).toContain('0 个视频')
    wrapper.unmount()
  })

  /**
   * 这一条是这份单测独有的：替身夹具的 `tagBody()` 永远带上 `video_count`，
   * 所以"后端没带这个字段"在浏览器那一路结构上量不到，只能在这里钉住视图的兜底。
   */
  it('says zero instead of nothing when the response omits the count', async () => {
    const wrapper = await mountTags([makeTag(1, '动作片')])

    // 摘掉 `?? 0` 的话，插值会渲染成空串，界面上就只剩一句光秃秃的「个视频」。
    expect(wrapper.find('.tag-meta').text().replace(/\s+/g, ' ').trim()).toBe('0 个视频')
    wrapper.unmount()
  })

  it('creates a tag with the typed name and the picked preset colour', async () => {
    const wrapper = await mountTags()
    await openCreate(wrapper)

    await nameField(wrapper).setValue('纪录片')
    // 预设色板第 3 个是 #e6a23c；点色块而不是往取色器里打字，走的是这条视图自己的分支。
    await dialog(wrapper).findAll('.preset-color')[2].trigger('click')
    await clickInDialog(wrapper, '创建')

    expect(createTag).toHaveBeenCalledWith({ name: '纪录片', color: '#e6a23c' })
    expect(ElMessage.success).toHaveBeenCalledWith('标签已创建')
    // 建完必须回读服务端那份，不能把本地填的形状当结果贴上去。
    expect(listTags).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('refuses to submit a name that is only whitespace', async () => {
    const wrapper = await mountTags()
    await openCreate(wrapper)

    await nameField(wrapper).setValue('   ')
    await clickInDialog(wrapper, '创建')

    expect(ElMessage.warning).toHaveBeenCalledWith('请输入标签名')
    expect(createTag).not.toHaveBeenCalled()
    expect(listTags).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  /**
   * #130：后端会裁掉首尾空格，界面也得裁——不然卡片上写的和存下去的是两个名字，
   * 而 `tags.name` 那个唯一列正好拦不住「动作片」与「动作片␣」这一对。
   */
  it('trims the padding off a created name', async () => {
    const wrapper = await mountTags()
    await openCreate(wrapper)

    await nameField(wrapper).setValue('  纪录片  ')
    await clickInDialog(wrapper, '创建')

    expect(createTag).toHaveBeenCalledWith({ name: '纪录片', color: '#409eff' })
    wrapper.unmount()
  })

  it('trims the padding off a renamed tag', async () => {
    const wrapper = await mountTags([ACTION])

    await clickInCard(wrapper, 0, '编辑')
    await nameField(wrapper).setValue(' 文艺片 ')
    await clickInDialog(wrapper, '更新')

    expect(updateTag).toHaveBeenCalledWith(1, { name: '文艺片' })
    wrapper.unmount()
  })

  it('treats a rename that only adds padding as no change at all', async () => {
    const wrapper = await mountTags([ACTION])

    await clickInCard(wrapper, 0, '编辑')
    await nameField(wrapper).setValue('动作片 ')
    await clickInDialog(wrapper, '更新')

    // 裁完之后同名，就不该发那次 PUT——这正是以前会写出第二条重复标签的那一下。
    expect(updateTag).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  /**
   * 编辑时**只发改动的那个字段**。这条形状在 e2e 里也能看到（那边断的是 PUT 的 body），
   * 但那边一次也量不到"名字没变而颜色变了"的反向组合，所以两边各钉半个岔路。
   */
  it('sends only the colour when the name was left alone', async () => {
    const wrapper = await mountTags()

    await clickInCard(wrapper, 0, '编辑')
    expect(nameValue(wrapper)).toBe('动作片')

    await dialog(wrapper).findAll('.preset-color')[1].trigger('click')
    await clickInDialog(wrapper, '更新')

    expect(updateTag).toHaveBeenCalledWith(1, { color: '#67c23a' })
    expect(vi.mocked(updateTag).mock.calls[0]?.[1]).not.toHaveProperty('name')
    wrapper.unmount()
  })

  it('does not write anything when the dialog was closed without a change', async () => {
    const wrapper = await mountTags()

    await clickInCard(wrapper, 0, '编辑')
    await clickInDialog(wrapper, '更新')

    expect(updateTag).not.toHaveBeenCalled()
    // 没改动就没有"标签已更新"这句谎。
    expect(ElMessage.success).not.toHaveBeenCalled()
    // 对话框照旧关闭、列表照旧回读，界面回到服务端的真相。
    expect(listTags).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows the server reason when the name is already taken', async () => {
    const wrapper = await mountTags()
    vi.mocked(createTag).mockRejectedValue(new Error('标签「动作片」已存在'))

    await openCreate(wrapper)
    await nameField(wrapper).setValue('动作片')
    await clickInDialog(wrapper, '创建')

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('标签「动作片」已存在'))
    // 失败时那次回读根本不该发生——重载会把人刚填的名字抹掉，而对话框还开着。
    expect(listTags).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('deletes a tag only after confirmation, then reloads', async () => {
    const wrapper = await mountTags()

    await clickInCard(wrapper, 0, '删除')

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(deleteTag).toHaveBeenCalledWith(1)
    expect(listTags).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('says nothing when the delete dialog is dismissed', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = await mountTags()

    await clickInCard(wrapper, 0, '删除')

    expect(deleteTag).not.toHaveBeenCalled()
    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(listTags).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('surfaces a failed load instead of showing an empty library', async () => {
    vi.mocked(listTags).mockRejectedValue(new Error('服务未就绪'))
    const wrapper = mount(Tags, { attachTo: document.body })
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('服务未就绪'))
    expect(wrapper.findAll('.tag-card')).toHaveLength(0)
    wrapper.unmount()
  })
})
