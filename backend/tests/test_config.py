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


def test_load_settings_from_env(monkeypatch):
    """Test that settings load from environment variables"""
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("API_HOST", "127.0.0.1")

    from src.config import Settings
    settings = Settings()

    assert settings.api_port == 9000
    assert settings.api_host == "127.0.0.1"


def test_invalid_port_raises_validation_error(monkeypatch):
    """Test that invalid port raises ValidationError"""
    monkeypatch.setenv("API_PORT", "invalid")

    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings()


def test_relative_thumbnail_path_anchors_at_backend_not_cwd(tmp_path, monkeypatch):
    """相对的 THUMBNAIL_PATH 按 backend/ 展开，不按进程的工作目录。

    库里存的是算出来的封面路径，读取端用 os.path.isfile 解析它；从别的目录
    启动服务就会让全库封面变成"无封面"。
    """
    from src.config import BACKEND_ROOT, Settings

    monkeypatch.chdir(tmp_path)
    anchored = Settings(_env_file=None, thumbnail_path="./data/thumbnails")

    assert os.path.isabs(anchored.thumbnail_path)
    assert anchored.thumbnail_path == os.path.normpath(
        str(BACKEND_ROOT / "data" / "thumbnails")
    )


def test_thumbnail_path_left_alone_when_absolute_or_empty(tmp_path, monkeypatch):
    """绝对路径（测试和部署里指到别处）与空值（关掉封面生成）都原样保留。"""
    from src.config import Settings

    monkeypatch.chdir(tmp_path)
    absolute = str(tmp_path / "covers")
    assert (
        Settings(_env_file=None, thumbnail_path=absolute).thumbnail_path == absolute
    )
    assert Settings(_env_file=None, thumbnail_path="").thumbnail_path == ""