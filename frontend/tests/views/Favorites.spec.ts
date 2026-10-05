/**
 * 收藏页的分页行为——这个视图此前一个测试都没有，而它的「移除」按钮会**改写页码本身**。
 *
 * 首页（`Home.vue`）在 #113 学到了这件事：地址栏里那一页可能已经不成立了，越界的那一页
 * 确实是空的，库里却不空，于是同屏出现「共 20 个」和一句"什么都没有"。收藏页走的是同一
 * 条路，触发方式却更日常——不需要分享链接，也不需要前进后退，只要在第 2 页把最后那一个
 * 收藏移掉：`total` 从 21 变成 20，`currentPage` 还停在 2。后端照实回 `items: []`、
 * `total: 20`，前端于是渲染 `el-empty` 那句「暂无收藏视频。」，而分页条的条件
 * `total > pageSize` 此刻正好不成立，**整个消失**——用户对着一个谎，连返回第 1 页的
 * 按钮都没了，只能刷新页面。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import Favorites from '@/views/Favorites.vue'
import { listFavorites, removeFavorite } from '@/api/favorites'
import { makeVideo } from '../factories'
import { CONFIRMED, buttonByText } from '../helpers'

vi.mock('@/api/favorites', () => ({
  listFavorites: vi.fn(),
  removeFavorite: vi.fn(),
  addFavorite: vi.fn(),
  checkFavorite: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

/** 每页 20 条是这个视图自己的默认值，夹具就按它排，不去动页大小选项。 */
const PAGE_SIZE = 20

/** 一份可控的收藏库：`serve` 按 page/page_size 切片，`remove` 真的把那一行删掉。 */
function library(ids: number[]) {
  const rows = [...ids]
  return {
    serve(page: number, pageSize: number) {
      const start = (page - 1) * pageSize
      return {
        items: rows.slice(start, start + pageSize).map((id) => makeVideo({ id, title: `第 ${id} 部` })),
        total: rows.length,
        page,
        page_size: pageSize,
      }
    },
    remove(id: number) {
      rows.splice(rows.indexOf(id), 1)
    },
  }
}

/**
 * 把两个 API 都接到同一份库上。分家写会漏掉 `removeFavorite`——那时"移除"只成功在
 * 提示框里，库里的行数一动没动，于是"移除后还剩几条"这类断言永远证不到东西。
 */
function wire(books: ReturnType<typeof library>) {
  vi.mocked(listFavorites).mockImplementation((page = 1, pageSize = PAGE_SIZE) =>
    Promise.resolve(books.serve(page, pageSize)),
  )
  vi.mocked(removeFavorite).mockImplementation(async (id: number) => {
    books.remove(id)
  })
}

/** 分页条上那个数字是唯一的换页入口，所以它本身也是被测的一环。 */
async function mountOnPage(page: number) {
  const wrapper = mount(Favorites)
  await flushPromises()
  const pager = wrapper.findAll('.el-pager li').find((node) => node.text() === String(page))
  if (!pager) throw new Error(`分页条上没有第 ${page} 页可以点`)
  await pager.trigger('click')
  await flushPromises()
  expect(vi.mocked(listFavorites)).toHaveBeenLastCalledWith(page, PAGE_SIZE)
  return wrapper
}

describe('Favorites', () => {
  beforeEach(() => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('loads the first page on mount', async () => {
    wire(library([1, 2, 3]))
    const wrapper = mount(Favorites)
    await flushPromises()

    expect(vi.mocked(listFavorites)).toHaveBeenCalledWith(1, PAGE_SIZE)
    expect(wrapper.findAll('.favorite-card')).toHaveLength(3)
  })

  it('asks the server for the page it clicks', async () => {
    wire(library(Array.from({ length: 21 }, (_, i) => i + 1)))
    const wrapper = await mountOnPage(2)

    expect(wrapper.findAll('.favorite-card')).toHaveLength(1)
  })

  it('clamps back to a page that still exists when the last favourite on the last page is removed', async () => {
    wire(library(Array.from({ length: 21 }, (_, i) => i + 1)))
    const wrapper = await mountOnPage(2)

    await buttonByText(wrapper, '移除').trigger('click')
    await flushPromises()

    expect(vi.mocked(removeFavorite)).toHaveBeenCalledWith(21)
    // 第 1 页、第 2 页、移除后又读第 2 页（那页此刻是空的），然后钳回第 1 页。
    expect(vi.mocked(listFavorites).mock.calls.map(([page]) => page)).toEqual([1, 2, 2, 1])
    expect(wrapper.findAll('.favorite-card')).toHaveLength(PAGE_SIZE)
    // 这句才是这条用例的落点：库里还有 20 个收藏，页面不能说「暂无收藏视频」。
    expect(wrapper.text()).not.toContain('暂无收藏视频')
  })

  it('keeps the user on the same page when that page still has items left', async () => {
    wire(library(Array.from({ length: 45 }, (_, i) => i + 1)))
    const wrapper = await mountOnPage(3) // 第 3 页只有 5 条

    await buttonByText(wrapper, '移除').trigger('click')
    await flushPromises()

    // 这一条挡的是"顺手回第 1 页"那种改法：用户的阅读位置不是 bug。
    expect(vi.mocked(listFavorites).mock.calls.map(([page]) => page)).toEqual([1, 3, 3])
    expect(wrapper.findAll('.favorite-card')).toHaveLength(4)
  })

  it('still says the library is empty when it really is', async () => {
    wire(library([]))
    const wrapper = mount(Favorites)
    await flushPromises()

    expect(wrapper.text()).toContain('暂无收藏视频')
  })

  it('leaves the page alone when the server call fails', async () => {
    vi.mocked(listFavorites).mockRejectedValue(new Error('服务未就绪'))
    const wrapper = mount(Favorites)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('服务未就绪'))
    expect(wrapper.findAll('.favorite-card')).toHaveLength(0)
  })
})
