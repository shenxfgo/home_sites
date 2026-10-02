# backend/src/config.py
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    @field_validator("thumbnail_path")
    @classmethod
    def _anchor_under_backend(cls, value: str) -> str:
        """把相对的封面目录按 backend/ 展开成绝对路径。

        ``Video.thumbnail_path`` 存的是当时算出来的字符串，读取端
        （``stream.py`` 的 ``os.path.isfile``）按进程的工作目录去解析它。
        于是从仓库根目录启动服务就会让全库封面变成"无封面"。
        """
        if not value or os.path.isabs(value):
            return value
        return os.path.normpath(BACKEND_ROOT / value)

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()