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
    database_url: str = "sqlite+aiosqlite:///./data/videos.db"
    # 用例跑在哪个库上。留空就是原来的内存 SQLite；填了就是拿真库跑测试，
    # conftest 与搬家脚本都读这一个出处，换库之后不用再另设环境变量。
    test_database_url: str = ""

    # Video Storage
    video_storage_path: str = "./data/videos"
    thumbnail_path: str = "./data/thumbnails"

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

    @field_validator("thumbnail_path", "backup_dir")
    @classmethod
    def _anchor_under_backend(cls, value: str) -> str:
        """把相对的封面/备份目录按 backend/ 展开成绝对路径。

        ``Video.thumbnail_path`` 存的是当时算出来的字符串，读取端
        （``stream.py`` 的 ``os.path.isfile``）按进程的工作目录去解析它。
        于是从仓库根目录启动服务就会让全库封面变成"无封面"。备份同理：
        相对目录会随启动位置写到不同的地方，等于没有固定去处。
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