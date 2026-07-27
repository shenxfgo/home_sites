# 视频列表前端页面实现计划

**目标：** 实现视频列表页面，展示视频卡片，支持搜索、筛选、分页。

**依赖：** VideoService API（已完成）

## 任务列表

### 任务 1：创建 TypeScript 类型定义

**文件：** `frontend/src/types/video.ts`

```typescript
export interface Video {
  id: number
  source_id: number
  filepath: string
  title: string | null
  description: string | null
  duration: number | null
  file_size: number | null
  format: string | null
  resolution: string | null
  thumbnail_path: string | null
  rating: number
  view_count: number
  last_played_at: string | null
  created_at: string
  updated_at: string
  tags: Tag[]
}

export interface Tag {
  id: number
  name: string
  color: string
}

export interface VideoListResponse {
  items: Video[]
  total: number
  page: number
  page_size: number
}

export interface VideoQueryParams {
  source_id?: number
  tag_id?: number
  search?: string
  page?: number
  page_size?: number
}
```

### 任务 2：创建视频 API 模块

**文件：** `frontend/src/api/videos.ts`

```typescript
import apiClient from './client'
import type { Video, VideoListResponse, VideoQueryParams } from '@/types/video'

export const videosApi = {
  list(params: VideoQueryParams): Promise<VideoListResponse>
  get(id: number): Promise<Video>
  update(id: number, data: Partial<Video>): Promise<Video>
  delete(id: number): Promise<void>
  getNew(sourceId?: number): Promise<Video[]>
  markViewed(id: number): Promise<void>
  play(id: number): Promise<void>
  updateProgress(id: number, progress: number): Promise<void>
}
```

### 任务 3：创建视频卡片组件

**文件：** `frontend/src/components/VideoCard.vue`

功能：
- 显示视频封面（默认占位图）
- 显示标题、时长、分辨率
- 显示评分（星级）
- 显示新视频标注（NEW/最近/本周）
- 点击跳转到视频详情

### 任务 4：创建视频列表页面

**文件：** `frontend/src/views/Home.vue`（替换现有占位）

功能：
- 视频网格布局
- 搜索框
- 来源筛选
- 分页组件
- 加载状态
- 空状态提示

### 任务 5：创建视频详情页面

**文件：** `frontend/src/views/VideoDetail.vue`（替换现有占位）

功能：
- 视频信息展示
- 播放按钮
- 编辑功能
- 删除功能
- 标签管理

### 任务 6：更新路由配置

**文件：** `frontend/src/router/index.ts`

更新视频详情路由。

### 任务 7：测试和提交

运行开发服务器测试，提交代码。

---

## 完成标准

1. ✅ 视频列表页面完成，支持搜索、筛选、分页
2. ✅ 视频卡片组件完成，显示封面、标题、时长、评分
3. ✅ 视频详情页面完成，支持编辑、删除
4. ✅ 新视频标注显示正确
5. ✅ 代码提交到 Git
