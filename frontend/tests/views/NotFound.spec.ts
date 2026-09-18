import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import NotFound from '@/views/NotFound.vue'
import { buttonByText } from '../helpers'

const router = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }))

vi.mock('vue-router', () => ({
  useRouter: () => router,
}))

describe('NotFound', () => {
  it('explains that the route does not exist', () => {
    const wrapper = mount(NotFound)

    expect(wrapper.find('.code').text()).toBe('404')
    expect(wrapper.find('.title').text()).toBe('页面不存在')
  })

  it('offers a way home and a way back', async () => {
    const wrapper = mount(NotFound)

    await buttonByText(wrapper, '回到首页').trigger('click')
    await buttonByText(wrapper, '返回上一页').trigger('click')

    expect(router.push).toHaveBeenCalledWith('/')
    expect(router.back).toHaveBeenCalled()
  })
})
