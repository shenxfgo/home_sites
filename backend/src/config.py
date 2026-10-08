# backend/src/config.py
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.backup import BackupError, parse_time_of_day

#: 相对路径的锚点。这里用文件位置而不是 cwd，是为了让配置与 uvicorn 从哪个目录
#: 启动无关 —— 见 ``_anchor_under_backend``。
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    # 默认连 PostgreSQL —— 真机跑的就是它。这里**故意不带口令**：口令只有一个去处，
    # 就是没进版本库的 `backend/.env`（模板见 `.env.example`，建库见
    # `deploy/pg-provision.example.sql`）。所以一份没有 `.env` 的检出会在第一次
    # 启动就报连不上库，这是想要的结果；旧的 SQLite 默认值会静默建出一个空文件、
    # 空库，看起来像"装好了"。要真用 SQLite（回滚、临时试跑）就把 `DATABASE_URL`
    # 指回 `sqlite+aiosqlite:///...`，见 README 的"回滚"。
    database_url: str = "postgresql+asyncpg://home_sites_app@127.0.0.1:5432/home_sites"
    # 用例跑在哪个库上。留空就是原来的内存 SQLite；填了就是拿真库跑测试，
    # conftest 与搬家脚本都读这一个出处，换库之后不用再另设环境变量。
    test_database_url: str = ""

    # Video Storage
    video_storage_path: str = "./data/videos"
    thumbnail_path: str = "./data/thumbnails"
    # 转码产物的去处。必须是**任何片源目录之外**的一处：扫描只走 `VideoSource.path`
    # 那几张表，也没有排除机制（`file_scanner.scan_directory` 的 `os.walk` 一路下潜），
    # 产物落在片源里面就会被扫成库里的第二行，同一个片子又能再转一遍（#154）。
    transcode_output_dir: str = "./data/transcode"

    # Object storage (any S3-compatible endpoint: MinIO, RustFS, Ceph, cloud)
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    # 自建 MinIO 常需要 "path"（http://host:9000/bucket/key）；留 auto 让 SDK 判断
    s3_addressing_style: str = "auto"

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Scan Settings
    default_scan_interval: int = 3600

    # Auth Settings
    session_hours: int = 12
    remember_me_days: int = 30
    auth_cookie_secure: bool = False
    login_max_failures: int = 5
    login_lockout_minutes: int = 10

    # Database backups (PostgreSQL only — the job is never armed on SQLite)
    backup_enabled: bool = True
    backup_dir: str = "./data/pg-backups"
    backup_keep_days: int = 7
    backup_time: str = "03:30"
    # Windows 上 PostgreSQL 的 bin 目录默认不在 PATH 里，指过去即可；
    # 留空则按 PATH 找 pg_dump / pg_restore。
    pg_bindir: str = ""

    @field_validator("thumbnail_path", "backup_dir", "transcode_output_dir")
    @classmethod
    def _anchor_under_backend(cls, value: str) -> str:
        """把相对的封面/备份/转码产物目录按 backend/ 展开成绝对路径。

        ``Video.thumbnail_path`` 存的是当时算出来的字符串，读取端
        （``stream.py`` 的 ``os.path.isfile``）按进程的工作目录去解析它。
        于是从仓库根目录启动服务就会让全库封面变成"无封面"。备份同理：
        相对目录会随启动位置写到不同的地方，等于没有固定去处。转码产物更是
        如此 —— 那串路径会**写进库里**（``transcode_outputs.output_path``），
        换个工作目录就读到自己昨天产的那一份了。
        """
        if not value or os.path.isabs(value):
            return value
        return os.path.normpath(BACKEND_ROOT / value)

    @field_validator("backup_time")
    @classmethod
    def _validate_backup_time(cls, value: str) -> str:
        """时刻写错要在启动时炸，别等到半夜任务静默失败。"""
        try:
            hour, minute = parse_time_of_day(value)
        except BackupError as exc:
            raise ValueError(str(exc)) from exc
        return f"{hour:02d}:{minute:02d}"

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
