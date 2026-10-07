"""Tests for subtitle API endpoints."""
from unittest.mock import patch

from src.models.source import VideoSource
from src.models.video import Video
from src.utils.media_streams import StreamNotFoundError
from src.utils.subtitles import SubtitleConversionError


async def _video_with_subtitle(
    db_session, tmp_path, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n"
):
    """Create a video plus a sidecar subtitle file on disk."""
    directory = tmp_path / "media"
    directory.mkdir(exist_ok=True)
    (directory / "movie.mp4").write_text("dummy", encoding="utf-8")
    subtitle_path = directory / "movie.zh.srt"
    subtitle_path.write_text(content, encoding="utf-8")

    source = VideoSource(name="Test Source", path=str(directory), type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath=str(directory / "movie.mp4"), title="Movie")
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video, subtitle_path


async def test_list_subtitles_is_empty_by_default(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.get(f"/api/videos/{video.id}/subtitles")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_list_and_delete_subtitle(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)

    created = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(subtitle_path)},
    )
    assert created.status_code == 201
    subtitle_id = created.json()["id"]
    assert created.json()["language"] == "zh"
    assert created.json()["label"] == "中文"

    listed = await client.get(f"/api/videos/{video.id}/subtitles")
    assert [item["id"] for item in listed.json()] == [subtitle_id]

    deleted = await client.delete(
        f"/api/videos/{video.id}/subtitles/{subtitle_id}"
    )
    assert deleted.status_code == 204

    after = await client.get(f"/api/videos/{video.id}/subtitles")
    assert after.json() == []


async def test_a_hand_registered_sidecar_gets_the_same_two_fields_as_a_scanned_one(
    client, db_session, tmp_path
):
    """手工 POST 和扫描必须派生出同一对 (language, label)。

    以前是两套：扫描走 `find_subtitle_files`（`language` 归一化、`label` 是后缀原文），
    手工这条路走 `subtitle_service._language_of/_label_of`，它自己从文件名里再切一次后缀，
    于是 `movie.chi.srt` 在这条路上 `language` 是 **`chi`**（没归一化，而那一列还要拿去当
    `srclang`），`movie.mp4.zh.srt` 更离谱——它切出来的是 `mp4.zh`，两个字段都是。
    """
    video, _ = await _video_with_subtitle(db_session, tmp_path)
    alias = tmp_path / "media" / "movie.chi.srt"
    alias.write_text("1\n00:00:01,000 --> 00:00:02,000\n哈喽\n", encoding="utf-8")
    fullname = tmp_path / "media" / "movie.mp4.zh.srt"
    fullname.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")

    aliased = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(alias)}
    )
    doubled = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(fullname)}
    )

    assert aliased.status_code == 201
    assert (aliased.json()["language"], aliased.json()["label"]) == ("zh", "中文")
    assert doubled.status_code == 201
    assert (doubled.json()["language"], doubled.json()["label"]) == ("zh", "中文")


async def test_registering_a_sidecar_whose_suffix_is_not_a_language_leaves_it_null(
    client, db_session, tmp_path
):
    """后缀不是语言代码时 `language` 得留空——那一列在真库上是 VARCHAR(10)。

    手工那条路以前把整个后缀当 `language` 存：`movie.导演评论.srt` 存成 `导演评论`（4 个字，
    刚好没炸），而任何超过 10 个字的说明性后缀在 PostgreSQL 上就是一次 `value too long`，
    界面上是一个 500。扫描那条路早就留空了，所以这是同一族文件、两种结果。
    """
    video, _ = await _video_with_subtitle(db_session, tmp_path)
    commentary = tmp_path / "media" / "movie.这条是导演评论加长版说明.srt"
    commentary.write_text("1\n00:00:01,000 --> 00:00:02,000\n旁白\n", encoding="utf-8")

    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(commentary)}
    )

    assert created.status_code == 201
    assert created.json()["language"] is None
    assert created.json()["label"] == "这条是导演评论加长版说明"


async def test_create_rejects_non_subtitle_extension(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(tmp_path / "media" / "movie.mp4")},
    )

    assert response.status_code == 400
    assert "不支持的字幕格式" in response.json()["detail"]


async def test_create_rejects_missing_file(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(tmp_path / "media" / "missing.zh.srt")},
    )

    assert response.status_code == 400
    assert "字幕文件不存在" in response.json()["detail"]


async def test_create_rejects_path_outside_video_directory(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)
    outside = tmp_path / "secret.zh.srt"
    outside.write_text("1\n", encoding="utf-8")

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(outside)},
    )

    assert response.status_code == 400
    assert "视频所在目录" in response.json()["detail"]


async def test_stream_converts_srt_to_webvtt(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )
    subtitle_id = created.json()["id"]

    response = await client.get(
        f"/api/videos/{video.id}/subtitles/{subtitle_id}/stream"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/vtt")
    assert response.text.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in response.text
    assert "你好" in response.text


async def test_stream_returns_404_for_unknown_subtitle(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.get(f"/api/videos/{video.id}/subtitles/999/stream")

    assert response.status_code == 404


async def test_stream_returns_404_when_file_disappeared(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )
    subtitle_path.unlink()

    response = await client.get(
        f"/api/videos/{video.id}/subtitles/{created.json()['id']}/stream"
    )

    assert response.status_code == 404


async def test_stream_reports_unconvertible_subtitle_as_415(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )

    reason = "Invalid data found when processing input"
    with patch(
        "src.api.subtitles.convert_to_webvtt",
        side_effect=SubtitleConversionError(f"字幕转换失败：{reason}"),
    ):
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/{created.json()['id']}/stream"
        )

    assert response.status_code == 415
    # 和上面内嵌那一条一样：415 只是状态，真正能用的是 ffmpeg 那句话有没有跟着走出来。
    assert "Invalid data found when processing input" in response.json()["detail"]


async def test_delete_unknown_subtitle_returns_404(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.delete(f"/api/videos/{video.id}/subtitles/4242")

    assert response.status_code == 404


PROBED = {
    "probed": True,
    "container": "matroska,webm",
    "subtitles": [
        {
            "stream_index": 1,
            "position": 0,
            "codec": "subrip",
            "language": "chi",
            "label": "简中",
            "supported": True,
        },
        {
            "stream_index": 2,
            "position": 1,
            "codec": "hdmv_pgs_subtitle",
            "language": None,
            "label": "轨道 2",
            "supported": False,
        },
    ],
    "audio": [
        {
            "stream_index": 3,
            "position": 0,
            "codec": "aac",
            "language": "chi",
            "label": "中文",
            "default": True,
        }
    ],
}


async def test_streams_lists_embedded_tracks(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    with patch("src.api.subtitles.probe_streams", return_value=PROBED):
        response = await client.get(f"/api/videos/{video.id}/subtitles/streams")

    assert response.status_code == 200
    body = response.json()
    assert body["container"] == "matroska,webm"
    # 'streams' is a fixed path, so it must not be parsed as a subtitle id.
    assert body["subtitles"][0]["label"] == "简中"
    assert body["subtitles"][1]["supported"] is False
    assert body["audio"][0]["default"] is True


async def test_streams_probes_the_video_path(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    with patch(
        "src.api.subtitles.probe_streams", return_value=PROBED
    ) as probe:
        await client.get(f"/api/videos/{video.id}/subtitles/streams")

    probe.assert_called_once_with(video.filepath)


async def test_streams_returns_404_for_unknown_video(client):
    with patch("src.api.subtitles.probe_streams", return_value=PROBED):
        response = await client.get("/api/videos/4242/subtitles/streams")

    assert response.status_code == 404
    assert response.json()["detail"] == "视频不存在"


async def test_embedded_stream_returns_webvtt(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)
    payload = "WEBVTT\n\n00:01.000 --> 00:02.000\n中文内嵌\n"

    with patch(
        "src.api.subtitles.extract_subtitle_webvtt", return_value=payload
    ) as extract:
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/embedded/1/stream"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/vtt")
    assert response.text == payload
    extract.assert_called_once_with(video.filepath, 1)


async def test_embedded_stream_returns_404_for_unknown_video(client):
    response = await client.get("/api/videos/4242/subtitles/embedded/1/stream")

    assert response.status_code == 404


async def test_embedded_stream_returns_404_when_file_disappeared(
    client, db_session, tmp_path
):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    with patch(
        "src.api.subtitles.extract_subtitle_webvtt", side_effect=FileNotFoundError
    ):
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/embedded/1/stream"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "视频文件不存在"


async def test_embedded_stream_returns_404_for_a_track_that_is_not_there(
    client, db_session, tmp_path
):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    with patch(
        "src.api.subtitles.extract_subtitle_webvtt",
        side_effect=StreamNotFoundError("文件里没有编号为 9 的字幕轨"),
    ):
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/embedded/9/stream"
        )

    assert response.status_code == 404
    assert "编号为 9" in response.json()["detail"]


async def test_embedded_stream_reports_unconvertible_track_as_415(
    client, db_session, tmp_path
):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    with patch(
        "src.api.subtitles.extract_subtitle_webvtt",
        side_effect=SubtitleConversionError("内嵌字幕提取失败：Unsupported codec"),
    ):
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/embedded/2/stream"
        )

    assert response.status_code == 415
    assert "Unsupported codec" in response.json()["detail"]
