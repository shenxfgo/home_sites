"""Tests for FastAPI main application."""
from fastapi.testclient import TestClient


def test_app_creation():
    """Test that FastAPI app can be created."""
    from src.main import app

    assert app is not None
    assert app.title == "Video Platform API"


def test_cors_middleware():
    """Test that CORS middleware is configured."""
    from src.main import app

    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            cors_middleware = middleware
            break

    assert cors_middleware is not None


def test_health_check():
    """Test health check endpoint."""
    from src.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_docs():
    """Test that API docs are available."""
    from src.main import app

    client = TestClient(app)
    response = client.get("/docs")

    assert response.status_code == 200


def test_redoc_available():
    """Test that ReDoc is available."""
    from src.main import app

    client = TestClient(app)
    response = client.get("/redoc")

    assert response.status_code == 200
