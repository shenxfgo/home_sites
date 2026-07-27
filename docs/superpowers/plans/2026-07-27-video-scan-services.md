# VideoService 和 ScanService 实现计划

**目标：** 实现视频管理和扫描服务的后端功能。

**技术栈：** Python 3.11+、FastAPI、SQLAlchemy 2.0+、aiosqlite

## 任务列表

### 任务 1：VideoService 视频服务

**文件：**
- 创建：`backend/src/services/video_service.py`

**接口：**
- 依赖：`src.models.video.Video`、`src.database.session.get_session`
- 产出：视频 CRUD 操作、搜索功能

**方法：**
```python
class VideoService:
    async def get_videos(
        self,
        source_id: int | None = None,
        tag_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Video], int]:
        """获取视频列表，支持筛选、搜索、分页"""

    async def get_video_by_id(self, video_id: int) -> Video | None:
        """获取单个视频详情"""

    async def update_video(self, video_id: int, **kwargs) -> Video:
        """更新视频信息"""

    async def delete_video(self, video_id: int) -> None:
        """删除视频"""

    async def get_new_videos(self, source_id: int | None = None) -> list[Video]:
        """获取新视频列表"""

    async def mark_video_viewed(self, video_id: int) -> None:
        """标记视频为已查看"""

    async def record_play(self, video_id: int) -> None:
        """记录播放"""

    async def update_progress(self, video_id: int, progress: int) -> None:
        """更新播放进度"""
```

### 任务 2：ScanService 扫描服务

**文件：**
- 创建：`backend/src/services/scan_service.py`
- 创建：`backend/src/utils/file_scanner.py`

**接口：**
- 依赖：`src.models.source.VideoSource`、`src.models.video.Video`、`src.models.new_video.NewVideo`
- 产出：文件扫描、新视频检测

**方法：**
```python
class ScanService:
    async def scan_source(self, source_id: int) -> dict:
        """扫描单个视频源"""

    async def scan_all_active(self) -> dict:
        """扫描所有活跃视频源"""

    async def get_scan_progress(self) -> dict:
        """获取扫描进度"""

    async def stop_scan(self) -> None:
        """停止扫描"""
```

**文件扫描工具：**
```python
# backend/src/utils/file_scanner.py
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'}

def scan_directory(path: str) -> list[dict]:
    """扫描目录，返回视频文件列表"""

def extract_video_info(filepath: str) -> dict:
    """提取视频信息（时长、分辨率等）"""

def generate_thumbnail(video_path: str, output_path: str) -> str:
    """生成视频缩略图"""
```

### 任务 3：视频管理 API

**文件：**
- 创建：`backend/src/api/videos.py`

**接口：**
- 依赖：`src.services.video_service.VideoService`
- 产出：视频 CRUD 端点

**端点：**
```
GET    /api/videos              # 获取视频列表
GET    /api/videos/{id}         # 获取视频详情
PUT    /api/videos/{id}         # 更新视频信息
DELETE /api/videos/{id}         # 删除视频
GET    /api/videos/new          # 获取新视频列表
POST   /api/videos/new/{id}/viewed  # 标记已查看
POST   /api/videos/{id}/play    # 开始播放
POST   /api/videos/{id}/progress  # 上报播放进度
```

### 任务 4：扫描服务 API

**文件：**
- 修改：`backend/src/api/sources.py`（添加扫描端点）
- 创建：`backend/src/api/scan.py`

**接口：**
- 依赖：`src.services.scan_service.ScanService`
- 产出：扫描服务端点

**端点：**
```
POST   /api/sources/{id}/scan   # 扫描视频源
POST   /api/scan/all            # 扫描所有视频源
GET    /api/scan/progress       # 获取扫描进度
POST   /api/scan/stop           # 停止扫描
```

### 任务 5：测试

**文件：**
- 创建：`backend/tests/test_services/test_video_service.py`
- 创建：`backend/tests/test_services/test_scan_service.py`
- 创建：`backend/tests/test_api/test_videos.py`
- 创建：`backend/tests/test_api/test_scan.py`

**要求：**
- 单元测试覆盖所有 Service 方法
- API 测试覆盖所有端点
- 测试通过

---

## 实现步骤

1. 实现 VideoService
2. 实现 ScanService 和文件扫描工具
3. 实现视频管理 API
4. 实现扫描服务 API
5. 编写测试
6. 运行测试验证
7. 提交代码

## 完成标准

1. ✅ VideoService 实现完成，支持 CRUD 和搜索
2. ✅ ScanService 实现完成，支持目录扫描
3. ✅ 视频管理 API 实现完成
4. ✅ 扫描服务 API 实现完成
5. ✅ 所有测试通过
6. ✅ 代码提交到 Git
