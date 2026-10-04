# tests/test_config.py
import os

import pytest
from pydantic import ValidationError


def test_load_default_settings():
    """Test that settings load with default values"""
    from src.config import Settings

    # `_env_file=None`：这条用例断言的是**代码里声明的默认值**，而开发者机器上的
    # backend/.env 现在指向 PostgreSQL（真库已经切过去了）。不关掉 dotenv 读取，
    # 任何人改自己的 .env 都会把这条用例弄红，而它想守的东西一点没变。
    settings = Settings(_env_file=None)

    assert settings.api_port == 8000
    assert settings.api_host == "0.0.0.0"
    assert "sqlite" in settings.database_url


def test_backup_defaults():
    """备份默认每晚开、留一周，且只在 PostgreSQL 上才会被挂载（挂载条件见 main）。"""
    from src.config import BACKEND_ROOT, Settings

    settings = Settings(_env_file=None)

    assert settings.backup_enabled is True
    assert settings.backup_keep_days == 7
    assert settings.backup_time == "03:30"
    assert settings.pg_bindir == ""
    # 相对目录和封面一样按 backend/ 锚定，否则会随 uvicorn 的启动位置漂移。
    assert settings.backup_dir == os.path.normpath(
        str(BACKEND_ROOT / "data" / "pg-backups")
    )


def test_a_bad_backup_time_fails_at_startup(monkeypatch):
    """时刻写错必须在启动时炸：静默的备份等于没有备份。"""
    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, backup_time="3am")

    # 补零、也接受不带前导 0 的写法
    assert Settings(_env_file=None, backup_time="3:05").backup_time == "03:05"


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
