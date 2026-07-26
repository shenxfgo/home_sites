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