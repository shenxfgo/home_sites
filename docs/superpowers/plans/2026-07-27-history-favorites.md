# 播放历史和收藏功能实现计划

**目标：** 实现播放历史和收藏功能。

**依赖：** PlayHistory 模型、Favorite 模型（已完成）

## 任务列表

### 任务 1：HistoryService 后端服务

**文件：**
- 创建：`backend/src/services/history_service.py`

**接口：**
```python
class HistoryService:
    async def get_history(page, page_size) -> tuple[list[PlayHistory], int]
    async def get_continue_list() -> list[Video]
    async def delete_history(history_id: int) -> None
```

### 任务 2：FavoriteService 后端服务

**文件：**
- 创建：`backend/src/services/favorite_service.py`

**接口：**
```python
class FavoriteService:
    async def get_favorites(page, page_size) -> tuple[list[Video], int]
    async def add_favorite(video_id: int) -> Favorite
    async def remove_favorite(video_id: int) -> None
    async def is_favorite(video_id: int) -> bool
```

### 任务 3：播放历史 API

**文件：**
- 创建：`backend/src/api/history.py`

**端点：**
```
GET    /api/history             # 获取播放历史
GET    /api/history/continue    # 获取继续播放列表
DELETE /api/history/{id}        # 删除历史记录
```

### 任务 4：收藏 API

**文件：**
- 创建：`backend/src/api/favorites.py`

**端点：**
```
GET    /api/favorites           # 获取收藏列表
POST   /api/favorites/{video_id}  # 添加收藏
DELETE /api/favorites/{video_id}  # 移除收藏
GET    /api/favorites/{video_id}/status  # 检查是否收藏
```

### 任务 5：注册路由

**文件：**
- 修改：`backend/src/main.py`

### 任务 6：前端 API 模块

**文件：**
- 创建：`frontend/src/api/history.ts`
- 创建：`frontend/src/api/favorites.ts`

### 任务 7：播放历史页面

**文件：**
- 修改：`frontend/src/views/History.vue`（替换占位）

**功能：**
- 播放历史列表
- 继续播放列表
- 删除历史记录
- 跳转到视频详情

### 任务 8：收藏列表页面

**文件：**
- 修改：`frontend/src/views/Favorites.vue`（替换占位）

**功能：**
- 收藏视频列表
- 取消收藏
- 跳转到视频详情

### 任务 9：更新视频详情页面

**文件：**
- 修改：`frontend/src/views/VideoDetail.vue`

添加收藏按钮。

### 任务 10：测试和提交

---

## 完成标准

1. ✅ HistoryService 实现完成
2. ✅ FavoriteService 实现完成
3. ✅ 播放历史 API 实现完成
4. ✅ 收藏 API 实现完成
5. ✅ 前端播放历史页面完成
6. ✅ 前端收藏列表页面完成
7. ✅ 测试通过
8. ✅ 代码提交到 Git
