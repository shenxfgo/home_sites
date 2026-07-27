# 标签管理功能实现计划

**目标：** 实现标签的 CRUD 和视频标签关联管理。

**依赖：** Tag 模型（已完成）、Video 模型（已完成）

## 任务列表

### 任务 1：TagService 后端服务

**文件：**
- 创建：`backend/src/services/tag_service.py`

**接口：**
```python
class TagService:
    async def create(name: str, color: str = "#409eff") -> Tag
    async def get_by_id(tag_id: int) -> Tag | None
    async def list_all() -> list[Tag]
    async def update(tag_id: int, **kwargs) -> Tag
    async def delete(tag_id: int) -> None
    async def get_videos_by_tag(tag_id: int) -> list[Video]
    async def add_tags_to_video(video_id: int, tag_ids: list[int]) -> None
    async def remove_tag_from_video(video_id: int, tag_id: int) -> None
```

### 任务 2：标签管理 API

**文件：**
- 创建：`backend/src/api/tags.py`

**端点：**
```
GET    /api/tags                # 获取标签列表
POST   /api/tags                # 创建标签
GET    /api/tags/{id}           # 获取单个标签
PUT    /api/tags/{id}           # 更新标签
DELETE /api/tags/{id}           # 删除标签
GET    /api/tags/{id}/videos    # 获取标签下的视频
POST   /api/videos/{id}/tags    # 批量添加标签
DELETE /api/videos/{id}/tags/{tag_id}  # 移除标签
```

### 任务 3：注册路由

**文件：**
- 修改：`backend/src/main.py`

添加 tags 路由。

### 任务 4：前端类型定义

**文件：**
- 修改：`frontend/src/types/video.ts`

添加标签相关类型。

### 任务 5：标签 API 模块

**文件：**
- 创建：`frontend/src/api/tags.ts`

### 任务 6：标签管理页面

**文件：**
- 修改：`frontend/src/views/Tags.vue`（替换占位）

**功能：**
- 标签列表展示
- 创建标签（对话框）
- 编辑标签
- 删除标签
- 标签颜色选择

### 任务 7：测试和提交

---

## 完成标准

1. ✅ TagService 实现完成
2. ✅ 标签 API 实现完成
3. ✅ 前端标签管理页面完成
4. ✅ 测试通过
5. ✅ 代码提交到 Git
