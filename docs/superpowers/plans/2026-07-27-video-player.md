# 视频播放器功能实现计划

**目标：** 实现视频播放功能，包括视频流 API 和前端播放器组件。

**依赖：** VideoService（已完成）、FFmpeg（视频处理）

## 任务列表

### 任务 1：视频流 API

**文件：**
- 创建：`backend/src/api/stream.py`

**接口：**
- 依赖：VideoService、视频文件路径
- 产出：视频流端点

**端点：**
```
GET /api/videos/{id}/stream          # 视频流（支持 Range 请求）
GET /api/videos/{id}/thumbnail       # 获取缩略图
```

**实现要点：**
- 支持 HTTP Range 请求（视频拖拽）
- Content-Type: video/mp4
- 支持大文件流式传输
- 缩略图生成和缓存

### 任务 2：缩略图生成工具

**文件：**
- 修改：`backend/src/utils/file_scanner.py`

**功能：**
```python
def generate_thumbnail(video_path: str, output_path: str, time: str = "00:00:01") -> str:
    """使用 FFmpeg 生成视频缩略图"""
```

### 任务 3：前端视频播放器组件

**文件：**
- 创建：`frontend/src/components/VideoPlayer.vue`

**功能：**
- HTML5 `<video>` 元素
- 播放/暂停控制
- 进度条拖拽
- 音量控制
- 全屏切换
- 播放进度上报（每30秒）
- 键盘快捷键

### 任务 4：更新视频详情页面

**文件：**
- 修改：`frontend/src/views/VideoDetail.vue`

**功能：**
- 集成 VideoPlayer 组件
- 播放按钮触发播放器显示
- 播放时隐藏其他信息

### 任务 5：注册新路由

**文件：**
- 修改：`backend/src/main.py`

添加 stream 路由。

### 任务 6：测试和提交

---

## 完成标准

1. ✅ 视频流 API 支持 Range 请求
2. ✅ 缩略图生成功能
3. ✅ 视频播放器组件完成
4. ✅ 播放进度自动上报
5. ✅ 代码提交到 Git
