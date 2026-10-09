"""Tests for SourceService CRUD operations."""
from datetime import datetime

import pytest


@pytest.mark.asyncio
async def test_create_source(db_session):
    """Test creating a video source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    source = await service.create(
        name="My Collection",
        path="/media/collection",
        type="local",
        scan_interval=1800,
    )

    assert source.id is not None
    assert source.name == "My Collection"
    assert source.path == "/media/collection"
    assert source.type == "local"
    assert source.scan_interval == 1800
    assert source.is_active is True


@pytest.mark.asyncio
async def test_create_source_defaults(db_session):
    """Test creating a source uses default values."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    source = await service.create(name="Default", path="/path", type="nas")

    assert source.scan_interval == 3600
    assert source.is_active is True


@pytest.mark.asyncio
async def test_list_sources(db_session):
    """Test listing all video sources."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    await service.create(name="Source 1", path="/path1", type="local")
    await service.create(name="Source 2", path="/path2", type="nas")
    await service.create(name="Source 3", path="/path3", type="minio")

    sources = await service.list_all()

    assert len(sources) == 3
    assert any(s.name == "Source 1" for s in sources)
    assert any(s.name == "Source 2" for s in sources)
    assert any(s.name == "Source 3" for s in sources)


@pytest.mark.asyncio
async def test_list_sources_active_only(db_session):
    """Test listing only active sources."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    await service.create(name="Active", path="/a", type="local")
    await service.create(name="Inactive", path="/b", type="local", is_active=False)

    active_sources = await service.list_all(active_only=True)

    assert len(active_sources) == 1
    assert active_sources[0].name == "Active"


@pytest.mark.asyncio
async def test_get_source_by_id(db_session):
    """Test getting a specific source by ID."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Test", path="/test", type="local")

    retrieved = await service.get_by_id(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "Test"


@pytest.mark.asyncio
async def test_get_source_not_found(db_session):
    """Test getting a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    result = await service.get_by_id(99999)

    assert result is None


@pytest.mark.asyncio
async def test_update_source(db_session):
    """Test updating a source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Original", path="/test", type="local")

    updated = await service.update(created.id, name="Updated", scan_interval=7200)

    assert updated.name == "Updated"
    assert updated.scan_interval == 7200
    assert updated.path == "/test"  # unchanged


@pytest.mark.asyncio
async def test_update_source_not_found(db_session):
    """Test updating a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    with pytest.raises(ValueError, match="Source with id 99999 not found"):
        await service.update(99999, name="test")


@pytest.mark.asyncio
async def test_delete_source(db_session):
    """Test deleting a source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="To Delete", path="/test", type="local")

    await service.delete(created.id)

    deleted = await service.get_by_id(created.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_source_not_found(db_session):
    """Test deleting a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    with pytest.raises(ValueError, match="Source with id 99999 not found"):
        await service.delete(99999)


@pytest.mark.asyncio
async def test_delete_source_removes_videos_and_dependents(db_session, user_id):
    """videos.source_id is NOT NULL, so a source with videos used to fail to delete."""
    from sqlalchemy import func, select

    from src.models.favorite import Favorite
    from src.models.history import PlayHistory
    from src.models.new_video import NewVideo
    from src.models.video import Video
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    doomed = await service.create(name="Doomed", path="/doomed", type="local")
    keeper = await service.create(name="Keeper", path="/keeper", type="local")

    doomed_video = Video(source_id=doomed.id, filepath="/doomed/a.mp4", title="a")
    keeper_video = Video(source_id=keeper.id, filepath="/keeper/b.mp4", title="b")
    db_session.add_all([doomed_video, keeper_video])
    await db_session.commit()

    db_session.add_all(
        [
            NewVideo(video_id=doomed_video.id, source_id=doomed.id),
            Favorite(user_id=user_id, video_id=doomed_video.id),
            PlayHistory(user_id=user_id, video_id=doomed_video.id, progress=42),
            NewVideo(video_id=keeper_video.id, source_id=keeper.id),
        ]
    )
    await db_session.commit()

    await service.delete(doomed.id)

    async def count(model):
        result = await db_session.execute(select(func.count()).select_from(model))
        return result.scalar()

    assert await count(Video) == 1
    assert await count(NewVideo) == 1
    assert await count(Favorite) == 0
    assert await count(PlayHistory) == 0
    assert await service.get_by_id(doomed.id) is None
    assert await service.get_by_id(keeper.id) is not None


@pytest.mark.asyncio
async def test_update_last_scan(db_session):
    """Test updating last_scan_at timestamp."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Test", path="/test", type="local")

    assert created.last_scan_at is None

    await service.update_last_scan(created.id)

    updated = await service.get_by_id(created.id)
    assert updated.last_scan_at is not None
    assert isinstance(updated.last_scan_at, datetime)


@pytest.mark.asyncio
async def test_delete_source_takes_the_covers_with_it(db_session, tmp_path):
    """删源与删影片走同一套级联，应用生成的封面也该一起走。"""
    from src.models.video import Video
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    doomed = await service.create(name="Doomed", path="/doomed", type="local")
    keeper = await service.create(name="Keeper", path="/keeper", type="local")

    doomed_cover = tmp_path / "doomed.jpg"
    doomed_cover.write_bytes(b"x")
    keeper_cover = tmp_path / "keeper.jpg"
    keeper_cover.write_bytes(b"x")

    doomed_video = Video(
        source_id=doomed.id, filepath="/doomed/a.mp4", title="a", thumbnail_path=str(doomed_cover)
    )
    keeper_video = Video(
        source_id=keeper.id, filepath="/keeper/b.mp4", title="b", thumbnail_path=str(keeper_cover)
    )
    db_session.add_all([doomed_video, keeper_video])
    await db_session.commit()

    await service.delete(doomed.id)

    assert not doomed_cover.exists()
    # 别的源的封面不能被带掉
    assert keeper_cover.exists()


@pytest.mark.asyncio
async def test_delete_source_takes_the_transcode_products_with_it(
    db_session, tmp_path, monkeypatch
):
    """⑦甲的第二条调用路径：删整个源和删一部影片走的是同一个级联，产物也得一起走。

    这一条值得单独钉，因为"收集"发生在级联函数里、"落盘"发生在**两个不同的调用方**里——
    只测删影片那一路的话，删源这一路忘记调落盘那句照样全绿。
    """
    from src.config import settings
    from src.models.transcode_output import TranscodeOutput
    from src.models.video import Video
    from src.services.source_service import SourceService

    root = tmp_path / "products"
    monkeypatch.setattr(settings, "transcode_output_dir", str(root))

    service = SourceService(db_session)
    doomed = await service.create(name="Doomed", path="/doomed", type="local")
    keeper = await service.create(name="Keeper", path="/keeper", type="local")

    doomed_video = Video(source_id=doomed.id, filepath="/doomed/a.mp4", title="a")
    keeper_video = Video(source_id=keeper.id, filepath="/keeper/b.mp4", title="b")
    db_session.add_all([doomed_video, keeper_video])
    await db_session.commit()

    doomed_product = root / str(doomed_video.id) / "a.mkv"
    keeper_product = root / str(keeper_video.id) / "b.mkv"
    for path in (doomed_product, keeper_product):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"a product")
    db_session.add_all(
        [
            TranscodeOutput(
                video_id=doomed_video.id, target_format="mkv", output_path=str(doomed_product)
            ),
            TranscodeOutput(
                video_id=keeper_video.id, target_format="mkv", output_path=str(keeper_product)
            ),
        ]
    )
    await db_session.commit()

    await service.delete(doomed.id)

    assert not doomed_product.exists()
    assert keeper_product.exists(), "别的源的产物不能被带掉"


@pytest.mark.asyncio
async def test_delete_source_unlinks_products_only_after_its_commit(
    db_session, tmp_path, monkeypatch
):
    """删源这一路的顺序半边：提交在前、落盘在后，和删影片那条同一个约定。

    两个调用方共用同一个级联，落盘却各自写在自己那一头——级联只报名字，谁先谁后由调用方定。
    所以这一条不能省：只测删影片那一路的话，删源这头把两句换了位置照样全绿。
    """
    from src.config import settings
    from src.models.transcode_output import TranscodeOutput
    from src.models.video import Video
    from src.services.source_service import SourceService

    root = tmp_path / "products"
    monkeypatch.setattr(settings, "transcode_output_dir", str(root))

    service = SourceService(db_session)
    doomed = await service.create(name="Doomed", path="/doomed", type="local")
    video = Video(source_id=doomed.id, filepath="/doomed/a.mp4", title="a")
    db_session.add(video)
    await db_session.commit()

    product = root / str(video.id) / "a.mkv"
    product.parent.mkdir(parents=True, exist_ok=True)
    product.write_bytes(b"a product")
    db_session.add(
        TranscodeOutput(video_id=video.id, target_format="mkv", output_path=str(product))
    )
    await db_session.commit()

    seen: list[bool] = []
    real_commit = db_session.commit

    async def commit_then_look() -> None:
        seen.append(product.exists())
        await real_commit()

    monkeypatch.setattr(db_session, "commit", commit_then_look)
    await service.delete(doomed.id)

    assert seen == [True], "落盘必须排在提交之后"
    assert not product.exists()
