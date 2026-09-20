"""Tests for Source API endpoints."""
import pytest

from src.api.sources import get_source_service
from src.services.source_service import SourceService


@pytest.fixture
async def extra_overrides(db_session):
    """The source route builds its service through this dependency."""

    async def override_get_source_service():
        return SourceService(db_session)

    return {get_source_service: override_get_source_service}


@pytest.mark.asyncio
async def test_list_sources_empty(client):
    """Test listing sources when empty."""
    response = await client.get("/api/sources")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_source(client):
    """Test creating a source."""
    data = {
        "name": "Test Collection",
        "path": "/test/path",
        "type": "local",
        "scan_interval": 3600,
    }

    response = await client.post("/api/sources", json=data)

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "Test Collection"
    assert result["path"] == "/test/path"
    assert result["type"] == "local"
    assert result["scan_interval"] == 3600
    assert result["is_active"] is True
    assert "id" in result
    assert "created_at" in result


@pytest.mark.asyncio
async def test_create_source_nas(client):
    """Test creating a NAS source."""
    data = {
        "name": "NAS Storage",
        "path": "/nas/videos",
        "type": "nas",
    }

    response = await client.post("/api/sources", json=data)

    assert response.status_code == 201
    result = response.json()
    assert result["type"] == "nas"


@pytest.mark.asyncio
async def test_create_source_minio(client):
    """Test creating a MinIO source."""
    data = {
        "name": "MinIO Bucket",
        "path": "bucket-name",
        "type": "minio",
    }

    response = await client.post("/api/sources", json=data)

    assert response.status_code == 201
    result = response.json()
    assert result["type"] == "minio"


@pytest.mark.asyncio
async def test_get_source(client):
    """Test getting a specific source."""
    # Create a source first
    create_data = {
        "name": "Test Source",
        "path": "/test/path",
        "type": "local",
    }
    create_response = await client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Get the source
    response = await client.get(f"/api/sources/{source_id}")

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == source_id
    assert result["name"] == "Test Source"


@pytest.mark.asyncio
async def test_get_nonexistent_source(client):
    """Test getting a source that doesn't exist."""
    response = await client.get("/api/sources/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found"


@pytest.mark.asyncio
async def test_update_source(client):
    """Test updating a source."""
    # Create a source first
    create_data = {"name": "Original", "path": "/test", "type": "local"}
    create_response = await client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Update the source
    update_data = {"name": "Updated", "scan_interval": 7200}
    response = await client.put(f"/api/sources/{source_id}", json=update_data)

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Updated"
    assert result["scan_interval"] == 7200
    assert result["path"] == "/test"  # unchanged


@pytest.mark.asyncio
async def test_update_source_not_found(client):
    """Test updating a source that doesn't exist."""
    update_data = {"name": "Updated"}
    response = await client.put("/api/sources/99999", json=update_data)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_source_empty_body(client):
    """Test updating a source with empty body."""
    create_data = {"name": "Test", "path": "/test", "type": "local"}
    create_response = await client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    response = await client.put(f"/api/sources/{source_id}", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "No fields to update"


@pytest.mark.asyncio
async def test_delete_source(client):
    """Test deleting a source."""
    # Create a source first
    create_data = {"name": "To Delete", "path": "/test", "type": "local"}
    create_response = await client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Delete the source
    response = await client.delete(f"/api/sources/{source_id}")

    assert response.status_code == 204

    # Verify it's deleted
    get_response = await client.get(f"/api/sources/{source_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_not_found(client):
    """Test deleting a source that doesn't exist."""
    response = await client.delete("/api/sources/99999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_source_invalid_type(client):
    """Test creating a source with invalid type."""
    data = {"name": "Invalid", "path": "/test", "type": "invalid"}

    response = await client.post("/api/sources", json=data)

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_source_missing_required_fields(client):
    """Test creating a source with missing required fields."""
    response = await client.post("/api/sources", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_sources_after_create_delete(client):
    """Test listing sources reflects create and delete operations."""
    # Initially empty
    response = await client.get("/api/sources")
    assert len(response.json()) == 0

    # Create two sources
    await client.post("/api/sources", json={"name": "S1", "path": "/1", "type": "local"})
    await client.post("/api/sources", json={"name": "S2", "path": "/2", "type": "nas"})

    response = await client.get("/api/sources")
    assert len(response.json()) == 2

    # Delete one
    sources = response.json()
    await client.delete(f"/api/sources/{sources[0]['id']}")

    response = await client.get("/api/sources")
    assert len(response.json()) == 1
