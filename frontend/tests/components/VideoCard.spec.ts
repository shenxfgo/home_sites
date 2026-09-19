import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import VideoCard from '@/components/VideoCard.vue'
import { makeTag, makeVideo } from '../factories'

const push = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function mountCard(video = makeVideo()) {
  return mount(VideoCard, { props: { video } })
}

describe('VideoCard', () => {
  it('points the thumbnail at the backend thumbnail route', () => {
    const wrapper = mountCard(makeVideo({ id: 12 }))

    const img = wrapper.find('img.thumbnail-img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/api/videos/12/thumbnail')
  })

  it('falls back to the placeholder when the video has no thumbnail', () => {
    const wrapper = mountCard(makeVideo({ thumbnail_path: null }))

    expect(wrapper.find('img.thumbnail-img').exists()).toBe(false)
    expect(wrapper.find('.thumbnail-placeholder').exists()).toBe(true)
  })

  it('formats durations as M:SS below an hour and H:MM:SS above', () => {
    expect(mountCard(makeVideo({ duration: 65 })).find('.duration-badge').text()).toBe('1:05')
    expect(mountCard(makeVideo({ duration: 3661 })).find('.duration-badge').text()).toBe('1:01:01')
  })

  it('hides the duration badge when the backend has no duration', () => {
    const wrapper = mountCard(makeVideo({ duration: null }))

    expect(wrapper.find('.duration-badge').exists()).toBe(false)
  })

  it('derives the title from the file name when the video is untitled', () => {
    const wrapper = mountCard(makeVideo({ title: null, filepath: 'D:\\videos\\深夜测试.mp4' }))

    expect(wrapper.find('.video-title').text()).toBe('深夜测试.mp4')
  })

  it('shows at most three tags and counts the rest', () => {
    const wrapper = mountCard(
      makeVideo({ tags: [makeTag(1), makeTag(2), makeTag(3), makeTag(4), makeTag(5)] }),
    )

    const tags = wrapper.findAll('.tag-row .el-tag')
    expect(tags).toHaveLength(4)
    expect(tags.at(-1)?.text()).toBe('+2')
  })

  it('badges an unwatched video as new however old its file is', () => {
    const monthOld = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()
    const wrapper = mountCard(makeVideo({ is_new: true, created_at: monthOld }))

    expect(wrapper.find('.new-badge').text()).toBe('新')
  })

  it('drops the badge once the video has been played', () => {
    const wrapper = mountCard(makeVideo({ is_new: false, created_at: new Date().toISOString() }))

    expect(wrapper.find('.new-badge').exists()).toBe(false)
  })

  it('opens the detail route for the card video on click', async () => {
    const wrapper = mountCard(makeVideo({ id: 9 }))

    await wrapper.find('.video-card').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'video-detail', params: { id: 9 } })
  })
})
