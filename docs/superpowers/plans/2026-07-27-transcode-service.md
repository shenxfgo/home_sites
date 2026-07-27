# 转码服务功能实现计划

**目标：** 实现视频转码功能，支持格式转换。

**依赖：** FFmpeg、Video 模型（已完成）

## 任务列表

### 任务 1：TranscodeService 后端服务

**文件：**
- 创建：`backend/src/services/transcode_service.py`

**接口：**
```python
class TranscodeService:
    async def transcode(video_id: int, target_format: str) -> dict
    async def get_status(video_id: int) -> dict
    async def cancel(video_id: int) -> None
```

### 任务 2：FFmpeg 工具模块

**文件：**
- 创建：`backend/src/utils/ffmpeg.py`

**功能：**
```python
def get_video_info(filepath: str) -> dict
def transcode_video(input_path: str, output_path: str, format: str) -> bool
def check_format_support(format: str) -> bool
```

### 任务 3：转码 API

**文件：**
- 创建：`backend/src/api/transcode.py`

**端点：**
```
POST   /api/transcode/{video_id}      # 转码视频
GET    /api/transcode/{video_id}/status  # 获取转码状态
POST   /api/transcode/{video_id}/cancel  # 取消转码
GET    /api/transcode/formats          # 获取支持的格式列表
```

### 任务 4：注册路由

**文件：**
- 修改：`backend/src/main.py`

### 任务 5：测试和提交

---

## 完成标准

1. ✅ TranscodeService 实现完成
2. ✅ FFmpeg 工具模块完成
3. ✅ 转码 API 实现完成
4. ✅ 测试通过
5. ✅ 代码提交到 Git
