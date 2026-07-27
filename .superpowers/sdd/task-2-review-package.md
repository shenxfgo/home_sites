# Review Package: Task 2

## Commit List
35b82c9 feat: add configuration management with environment variables

## Diff Stats
backend/.env.example         | 17 +++++++++++++++++
backend/pyproject.toml       |  6 +++++-
backend/src/__init__.py      |  0
backend/src/config.py        | 39 +++++++++++++++++++++++++++++++++++++++
backend/tests/conftest.py    |  6 ++++++
backend/tests/test_config.py | 36 ++++++++++++++++++++++++++++++++++++
6 files changed, 103 insertions(+), 1 deletion(-)

## Full Diff

```diff
diff --git a/backend/.env.example b/backend/.env.example
new file mode 100644
index 0000000..524766a
--- /dev/null
+++ b/backend/.env.example
@@ -0,0 +1,17 @@
+# Database
+DATABASE_URL=sqlite+aiosqlite:///./data/videos.db
+
+# Video Storage
+VIDEO_STORAGE_PATH=./data/videos
+THUMBNAIL_PATH=./data/thumbnails
+
+# API Settings
+API_HOST=0.0.0.0
+API_PORT=8000
+API_RELOAD=true
+
+# CORS
+CORS_ORIGINS=http://localhost:3000,http://localhost:5173
+
+# Scan Settings
+DEFAULT_SCAN_INTERVAL=3600
\ No newline at file at end
diff --git a/backend/pyproject.toml b/backend/pyproject.toml
index 7b0466c..47f1ca2 100644
--- a/backend/pyproject.toml
+++ b/backend/pyproject.toml
@@ -33,6 +33,9 @@ dev = [
 requires = ["hatchling"]
 build-backend = "hatchling.build"
 
+[tool.hatch.build.targets.wheel]
+packages = ["src"]
+
 [tool.black]
 line-length = 100
 target-version = ['py311']
@@ -50,4 +53,5 @@ disallow_untyped_defs = true
 
 [tool.pytest.ini_options]
 asyncio_mode = "auto"
-testpaths = ["tests"]
\ No newline at file at end
diff --git a/backend/src/__init__.py b/backend/src/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/src/config.py b/backend/src/config.py
new file mode 100644
index 0000000..05ba734
--- /dev/null
+++ b/backend/src/config.py
@@ -0,0 +1,39 @@
+# backend/src/config.py
+from pydantic_settings import BaseSettings, SettingsConfigDict
+
+
+class Settings(BaseSettings):
+    """Application configuration loaded from environment variables."""
+
+    model_config = SettingsConfigDict(
+        env_file=".env",
+        env_file_encoding="utf-8",
+        case_sensitive=False,
+        extra="ignore",
+    )
+
+    # Database
+    database_url: str = "sqlite+aiosqlite:///./data/videos.db"
+
+    # Video Storage
+    video_storage_path: str = "./data/videos"
+    thumbnail_path: str = "./data/thumbnails"
+
+    # API Settings
+    api_host: str = "0.0.0.0"
+    api_port: int = 8000
+    api_reload: bool = True
+
+    # CORS
+    cors_origins: str = "http://localhost:3000,http://localhost:5173"
+
+    # Scan Settings
+    default_scan_interval: int = 3600
+
+    def get_cors_origins_list(self) -> list[str]:
+        """Parse CORS origins from comma-separated string."""
+        return [origin.strip() for origin in self.cors_origins.split(",")]
+
+
+# Global settings instance
+settings = Settings()
\ No newline at file at end
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
new file mode 100644
index 0000000..c7a8a98
--- /dev/null
+++ b/backend/tests/conftest.py
@@ -0,0 +1,6 @@
+import sys
+from pathlib import Path
+
+# Add parent directory to Python path so 'src' becomes importable
+backend_dir = Path(__file__).parent.parent
+sys.path.insert(0, str(backend_dir))
\ No newline at file at end
diff --git a/backend/tests/test_config.py b/backend/tests/test_config.py
new file mode 100644
index 0000000..1251bd6
--- /dev/null
+++ b/backend/tests/test_config.py
@@ -0,0 +1,36 @@
+# tests/test_config.py
+import os
+from pydantic import ValidationError
+import pytest
+
+def test_load_default_settings():
+    """Test that settings load with default values"""
+    from src.config import Settings
+
+    settings = Settings()
+
+    assert settings.api_port == 8000
+    assert settings.api_host == "0.0.0.0"
+    assert "sqlite" in settings.database_url
+
+
+def test_load_settings_from_env():
+    """Test that settings load from environment variables"""
+    os.environ["API_PORT"] = "9000"
+    os.environ["API_HOST"] = "127.0.0.1"
+
+    from src.config import Settings
+    settings = Settings()
+
+    assert settings.api_port == 9000
+    assert settings.api_host == "127.0.0.1"
+
+
+def test_invalid_port_raises_validation_error():
+    """Test that invalid port raises ValidationError"""
+    os.environ["API_PORT"] = "invalid"
+
+    from src.config import Settings
+
+    with pytest.raises(ValidationError):
+        Settings()
\ No newline at file at end
```