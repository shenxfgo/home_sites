"""Tests for FastAPI main application."""
import httpx
import pytest_asyncio

from src.main import app


@pytest_asyncio.fixture
async def public_client():
    """A client for the routes that stay open before login.

    Deliberately built here rather than from ``conftest``'s ``anon_client``: that
    one patches the session factory and the DB dependency, and none of the three
    routes below touch either.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


def test_app_creation():
    """Test that FastAPI app can be created."""
    assert app is not None
    assert app.title == "Video Platform API"


def test_cors_middleware():
    """Test that CORS middleware is configured."""
    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            cors_middleware = middleware
            break

    assert cors_middleware is not None


async def test_health_check(public_client):
    """Test health check endpoint."""
    response = await public_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_api_docs(public_client):
    """Test that API docs are available."""
    response = await public_client.get("/docs")

    assert response.status_code == 200


async def test_redoc_available(public_client):
    """Test that ReDoc is available."""
    response = await public_client.get("/redoc")

    assert response.status_code == 200
