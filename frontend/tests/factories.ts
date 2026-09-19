import type { Source } from '@/types/source'
import type { Subtitle } from '@/types/subtitle'
import type { SeriesProgress, Tag, Video } from '@/types/video'

export function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    id: 1,
    name: '本地视频库',
    path: 'D:\\videos',
    type: 'local',
    scan_interval: 3600,
    last_scan_at: null,
    is_active: true,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

export function makeTag(id: number, name = `标签${id}`): Tag {
  return { id, name, color: '#7c6cff' }
}

export function makeSubtitle(overrides: Partial<Subtitle> = {}): Subtitle {
  return {
    id: 1,
    video_id: 1,
    language: 'zh',
    filepath: 'D:\\videos\\sample.zh.srt',
    label: '中文',
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

export function makeVideo(overrides: Partial<Video> = {}): Video {
  return {
    id: 1,
    source_id: 1,
    filepath: '/data/videos/sample.mp4',
    title: '示例视频',
    description: null,
    duration: 65,
    file_size: 1024,
    format: 'mp4',
    resolution: '640x480',
    thumbnail_path: '/data/thumbs/sample.jpg',
    series: null,
    season: null,
    episode: null,
    is_missing: false,
    rating: 3,
    view_count: 7,
    is_new: false,
    progress: null,
    last_played_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: [],
    ...overrides,
  }
}

export function makeSeriesProgress(overrides: Partial<SeriesProgress> = {}): SeriesProgress {
  return {
    series: '暗涌',
    total: 3,
    finished: 1,
    watched: 2,
    next: makeVideo({ id: 11, series: '暗涌', season: 1, episode: 2 }),
    ...overrides,
  }
}
