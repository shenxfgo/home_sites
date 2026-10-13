"""Tests for Source API endpoints."""
import pytest

from src.api.sources import get_source_service
from src.main import app
from src.services.source_service import SourceService
from tests.support import ensure_source


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
        "path": "s3://bucket-name/shows",
        "type": "minio",
    }

    response = await client.post("/api/sources", json=data)

    assert response.status_code == 201
    result = response.json()
    assert result["type"] == "minio"


@pytest.mark.asyncio
async def test_create_minio_source_requires_s3_path(client):
    """A MinIO source typed as a plain folder would scan an empty bucket in silence."""
    response = await client.post(
        "/api/sources",
        json={"name": "Bad MinIO", "path": "/mnt/videos", "type": "minio"},
    )

    assert response.status_code == 400
    assert "s3://" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_local_source_rejects_s3_path(client):
    """An s3:// path under a local type would walk a directory literally named 's3:'."""
    response = await client.post(
        "/api/sources",
        json={"name": "Bad Local", "path": "s3://bucket/shows", "type": "local"},
    )

    assert response.status_code == 400
    assert "MinIO" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_source_path_must_match_stored_type(client):
    """The check uses the type already on the row, not just the fields sent now."""
    create = await client.post(
        "/api/sources",
        json={"name": "Bucket", "path": "s3://bucket/shows", "type": "minio"},
    )
    source_id = create.json()["id"]

    response = await client.put(f"/api/sources/{source_id}", json={"path": "/mnt/videos"})

    assert response.status_code == 400
    assert "s3://" in response.json()["detail"]


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
    assert response.json()["detail"] == "视频源不存在"


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
    assert response.json()["detail"] == "没有需要更新的字段"


# 这五列在 `src/models/source.py` 里全是 NOT NULL，而 `SourceUpdate` 五项全标了 `| None`。
# 键是接口字段名（422 的 loc 用它），值是那句中文里的主语（界面 `SourceForm.vue` 的叫法）。
_NOT_NULL_COLUMNS = {
    "name": "名称",
    "path": "路径",
    "type": "类型",
    "scan_interval": "扫描间隔",
    "is_active": "启用状态",
}
_SEEDED_SOURCE = {
    "name": "原始名",
    "path": "/seeded/path",
    "type": "nas",
    "scan_interval": 7200,
    "is_active": False,
}


async def _seed_source(client) -> int:
    response = await client.post("/api/sources", json=dict(_SEEDED_SOURCE))
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("column", "label"), _NOT_NULL_COLUMNS.items())
async def test_an_explicit_null_cannot_clear_a_not_null_column(client, column, label):
    """差量 PUT 里显式 null 是「要清空这一列」，不是「没填这一项」——而这五列清不得（#211 ①甲）。

    `data.model_dump(exclude_unset=True)` 会把显式 null 收进差量，`None` 一路走到 `setattr`
    和那次 commit：name/type/scan_interval/is_active 四格撞数据库的 NotNullViolation，
    `path` 那格更早在路由那句 `_check_path_shape` 里就 AttributeError（它对 path 调
    `.startswith`）。两条都落在 `except ValueError` 的射程之外，真服务器上就是 500。
    """
    source_id = await _seed_source(client)

    response = await client.put(f"/api/sources/{source_id}", json={column: None})

    assert response.status_code == 422, response.text
    # ⑨甲：422 里那句话必须是光秃秃的中文，不带 pydantic 那句「Value error, 」包装。
    assert response.json()["detail"][0]["msg"] == f"{label}不能留空"
    # 拒绝发生在写库之前：整行还是播种时的样子。
    fresh = (await client.get(f"/api/sources/{source_id}")).json()
    assert {column: fresh[column] for column in _NOT_NULL_COLUMNS} == _SEEDED_SOURCE


@pytest.mark.asyncio
async def test_a_patch_that_omits_the_other_columns_still_works(client):
    """③甲：闸口只挡显式 null，「省略」这条路照旧是不改。

    少了这条，上面那五格可以靠「五列全变必填」蒙绿——而 `SourceForm.vue` 发的正是只带改动
    那几项的差量，一次改名会连带把路径、类型、间隔、开关四项按播种值撞回去。
    """
    source_id = await _seed_source(client)

    response = await client.put(f"/api/sources/{source_id}", json={"name": "只改名字"})

    assert response.status_code == 200, response.text
    fresh = (await client.get(f"/api/sources/{source_id}")).json()
    assert fresh["name"] == "只改名字"
    assert {column: fresh[column] for column in _NOT_NULL_COLUMNS if column != "name"} == {
        column: value for column, value in _SEEDED_SOURCE.items() if column != "name"
    }


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


@pytest.mark.asyncio
async def test_the_request_session_reaches_the_service_through_the_real_dependency(
    client, db_session
):
    """这个文件的夹具一直替 ``get_source_service`` 站着，所以函数体一次也没被执行过。

    撤掉替身，让真依赖自己接一次请求：它得把这条请求的 session 交出去，否则读不到
    同一个库里那行片源——替身演得再像，也不替接线负责。

    电池 M6（#198）：把那句改成 `SourceService(None)`，红的就是这一条（请求 500）。
    本文件其余用例一条也不红：它们走的还是替身，这一格恰好说明「被替身演掉」是覆盖
    率上最难看见的一种绿。
    """
    app.dependency_overrides.pop(get_source_service, None)
    await ensure_source(db_session, source_id=7)

    response = await client.get("/api/sources")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["source-7"]
