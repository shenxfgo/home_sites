# 视频管理平台后端

视频管理平台的后端 API 服务。

## 开发

```bash
# 安装依赖
uv sync

# 运行开发服务器
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## 测试

```bash
# 运行测试
uv run pytest

# 运行并生成覆盖率报告
uv run pytest --cov=src --cov-report=html
```
