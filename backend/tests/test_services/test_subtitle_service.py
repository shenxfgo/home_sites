"""Tests for SubtitleService operations."""
import os

import pytest
from sqlalchemy import select

from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.video import Video
from src.services.subtitle_service import SubtitleService


async def _video_with_dir(session, tmp_path, name="movie.mp4"):
    """Create a source + video whose file really exists in a temp directory."""
    directory = tmp_path / "media"
    directory.mkdir()
    filepath = directory / name
    filepath.write_text("dummy", encoding="utf-8")

    source = VideoSource(name="Test Source", path=str(directory), type="local")
    session.add(source)
    await session.commit()

    video = Video(source_id=source.id, filepath=str(filepath), title="Movie")
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return source, video, directory


async def test_list_for_video_returns_only_that_video(db_session, tmp_path):
    source, video, directory = await _video_with_dir(db_session, tmp_path)
    other_video = Video(source_id=source.id, filepath=str(directory / "other.mp4"))
    db_session.add(other_video)
    await db_session.commit()
    db_session.add(
        Subtitle(video_id=video.id, filepath=str(directory / "movie.zh.srt"), label="zh")
    )
    await db_session.commit()

    service = SubtitleService(db_session)
    mine = await service.list_for_video(video.id)
    theirs = await service.list_for_video(other_video.id)

    assert [s.label for s in mine] == ["zh"]
    assert theirs == []


async def test_add_registers_sidecar_and_derives_language(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)
    subtitle_path = directory / "movie.zh.srt"
    subtitle_path.write_text("1\n", encoding="utf-8")

    service = SubtitleService(db_session)
    subtitle = await service.add(video.id, str(subtitle_path))

    assert subtitle.id is not None
    assert subtitle.language == "zh"
    assert subtitle.label == "zh"


async def test_add_keeps_explicit_language_and_label(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)
    subtitle_path = directory / "movie.srt"
    subtitle_path.write_text("1\n", encoding="utf-8")

    service = SubtitleService(db_session)
    subtitle = await service.add(
        video.id, str(subtitle_path), language="zh", label="中文"
    )

    assert (subtitle.language, subtitle.label) == ("zh", "中文")


async def test_add_rejects_unknown_video(db_session, tmp_path):
    _, _, directory = await _video_with_dir(db_session, tmp_path)
    subtitle_path = directory / "movie.srt"
    subtitle_path.write_text("1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not found"):
        await SubtitleService(db_session).add(9999, str(subtitle_path))


async def test_add_rejects_missing_file(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)

    with pytest.raises(ValueError, match="字幕文件不存在"):
        await SubtitleService(db_session).add(video.id, str(directory / "nope.srt"))


async def test_add_rejects_path_outside_video_directory(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)
    outside = tmp_path / "elsewhere.srt"
    outside.write_text("1\n", encoding="utf-8")

    service = SubtitleService(db_session)
    with pytest.raises(ValueError, match="视频所在目录"):
        await service.add(video.id, str(outside))

    result = await db_session.execute(select(Subtitle))
    assert result.scalars().all() == []


async def test_delete_removes_the_record(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)
    subtitle = Subtitle(video_id=video.id, filepath=str(directory / "movie.srt"))
    db_session.add(subtitle)
    await db_session.commit()

    service = SubtitleService(db_session)
    await service.delete(video.id, subtitle.id)

    assert await service.list_for_video(video.id) == []


async def test_delete_unknown_subtitle_raises(db_session, tmp_path):
    _, video, _ = await _video_with_dir(db_session, tmp_path)

    with pytest.raises(ValueError, match="not found"):
        await SubtitleService(db_session).delete(video.id, 1234)


async def test_known_paths_covers_the_whole_source(db_session, tmp_path):
    source, video, directory = await _video_with_dir(db_session, tmp_path)
    db_session.add(
        Subtitle(video_id=video.id, filepath=os.path.join(directory, "movie.zh.srt"))
    )
    await db_session.commit()

    known = await SubtitleService(db_session).known_paths(source.id)

    assert known == {os.path.normpath(os.path.join(str(directory), "movie.zh.srt"))}


async def test_register_skips_known_paths_and_adds_the_rest(db_session, tmp_path):
    _, video, directory = await _video_with_dir(db_session, tmp_path)
    first = os.path.join(str(directory), "movie.zh.srt")
    second = os.path.join(str(directory), "movie.en.srt")
    known = {os.path.normpath(first)}
    service = SubtitleService(db_session)

    assert service.register(video.id, {"filepath": first, "language": "zh", "label": "zh"}, known) is False
    assert service.register(video.id, {"filepath": second, "language": "en", "label": "en"}, known) is True
    await db_session.commit()

    stored = await service.list_for_video(video.id)

    assert [s.filepath for s in stored] == [os.path.normpath(second)]
    assert known == {os.path.normpath(first), os.path.normpath(second)}
