# 自动扫描定时任务功能实现计划

**目标：** 实现基于 APScheduler 的自动扫描定时任务。

**依赖：** APScheduler（已安装）、ScanService（已完成）

## 任务列表

### 任务 1：调度器配置

**文件：**
- 创建：`backend/src/scheduler/__init__.py`
- 创建：`backend/src/scheduler/scan_scheduler.py`

**接口：**
```python
class ScanScheduler:
    def __init__(self)
    def start(self)
    def stop(self)
    def add_source_job(source_id: int, interval: int)
    def remove_source_job(source_id: int)
    def get_jobs(self) -> list[dict]
```

### 任务 2：扫描任务函数

**文件：**
- 创建：`backend/src/scheduler/tasks.py`

**功能：**
```python
async def scan_source_task(source_id: int)
async def scan_all_active_task()
```

### 任务 3：集成到应用生命周期

**文件：**
- 修改：`backend/src/main.py`

在应用启动时启动调度器，关闭时停止。

### 任务 4：调度器管理 API

**文件：**
- 创建：`backend/src/api/scheduler.py`

**端点：**
```
GET    /api/scheduler/jobs       # 获取所有定时任务
POST   /api/scheduler/jobs       # 添加定时任务
DELETE /api/scheduler/jobs/{id}  # 删除定时任务
GET    /api/scheduler/status     # 获取调度器状态
```

### 任务 5：测试和提交

---

## 完成标准

1. ✅ APScheduler 集成完成
2. ✅ 定时扫描任务实现完成
3. ✅ 调度器管理 API 实现完成
4. ✅ 应用生命周期集成完成
5. ✅ 测试通过
6. ✅ 代码提交到 Git
