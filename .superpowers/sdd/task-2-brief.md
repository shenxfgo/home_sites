# Task 2: Create Configuration Management

**Files:**
- Create: `backend/src/config.py`
- Create: `backend/.env.example`

**Interfaces:**
- Consumes: pydantic-settings from pyproject.toml
- Produces: `Settings` class with environment-based configuration

## Steps

### Step 1: Create .env.example with configuration template

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/videos.db

# Video Storage
VIDEO_STORAGE_PATH=./data/videos
THUMBNAIL_PATH=./data/thumbnails

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Scan Settings
DEFAULT_SCAN_INTERVAL=3600
```

### Step 2: Write the failing test for configuration

```python
# tests/test_config.py
import os
from pydantic import ValidationError
import pytest

def test_load_default_settings():
    """Test that settings load with default values"""
    from src.config import Settings

    settings = Settings()

    assert settings.api_port == 8000
    assert settings.api_host == "0.0.0.0"
    assert "sqlite" in settings.database_url


def test_load_settings_from_env():
    """Test that settings load from environment variables"""
    os.environ["API_PORT"] = "9000"
    os.environ["API_HOST"] = "127.0.0.1"

    from src.config import Settings
    settings = Settings()

    assert settings.api_port == 9000
    assert settings.api_host == "127.0.0.1"


def test_invalid_port_raises_validation_error():
    """Test that invalid port raises ValidationError"""
    os.environ["API_PORT"] = "invalid"

    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings()
```

### Step 3: Run test to verify it fails

```bash
cd backend
uv run pytest tests/test_config.py -v
```
Expected: FAIL with "function not defined"

### Step 4: Write minimal implementation of config.py

```python
# backend/src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Scan Settings
    default_scan_interval: int = 3600

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
```

### Step 5: Run test to verify it passes

```bash
cd backend
uv run pytest tests/test_config.py -v
```
Expected: PASS

### Step 6: Commit

```bash
cd backend
git add src/config.py .env.example tests/test_config.py
git commit -m "feat: add configuration management with environment variables"
```