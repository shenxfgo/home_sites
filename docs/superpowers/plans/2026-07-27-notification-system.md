# 通知系统功能实现计划

**目标：** 实现通知系统，支持扫描完成、新视频提醒等通知。

**依赖：** Notification 模型（已完成）

## 任务列表

### 任务 1：NotificationService 后端服务

**文件：**
- 创建：`backend/src/services/notification_service.py`

**接口：**
```python
class NotificationService:
    async def create(type: str, title: str, message: str, data: dict = None) -> Notification
    async def get_notifications(page, page_size) -> tuple[list[Notification], int]
    async def get_unread_count() -> int
    async def mark_read(notification_id: int) -> None
    async def mark_all_read() -> None
```

### 任务 2：通知 API

**文件：**
- 创建：`backend/src/api/notifications.py`

**端点：**
```
GET    /api/notifications       # 获取通知列表
GET    /api/notifications/unread # 获取未读数量
POST   /api/notifications/{id}/read  # 标记已读
POST   /api/notifications/read-all  # 全部标记已读
```

### 任务 3：注册路由

**文件：**
- 修改：`backend/src/main.py`

### 任务 4：集成通知到扫描服务

**文件：**
- 修改：`backend/src/services/scan_service.py`

扫描完成后自动创建通知。

### 任务 5：前端 API 模块

**文件：**
- 创建：`frontend/src/api/notifications.ts`

### 任务 6：通知中心组件

**文件：**
- 创建：`frontend/src/components/NotificationCenter.vue`

**功能：**
- 通知列表
- 未读数量角标
- 标记已读
- 全部标记已读
- 通知类型图标

### 任务 7：集成到主布局

**文件：**
- 修改：`frontend/src/layouts/MainLayout.vue`

### 任务 8：测试和提交

---

## 完成标准

1. ✅ NotificationService 实现完成
2. ✅ 通知 API 实现完成
3. ✅ 扫描服务集成通知
4. ✅ 前端通知中心组件完成
5. ✅ 测试通过
6. ✅ 代码提交到 Git
