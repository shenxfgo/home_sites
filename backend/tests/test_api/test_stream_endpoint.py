"""播放与封面这两条读路径，此前只在外层函数上被测过，从接口进来一次也没走过。

#159：`api/stream.py` 72%，缺的十七行是 `37, 44-59, 90-100, 105-116`——同十七行
在只跑 16 条用例的子集和跑满 786 条的套件里读数一模一样，说明这一整条读路径在
pytest 这套里是**整体盲区**，不是某条分支漏了：`tests/test_api/test_stream.py` 直接调
`_handle_range_request`，Range 的边界语义有真文件签字，但路由本身（content-type 怎么
挑、本地文件交给 `FileResponse`、对象存储没有本地文件所以走"从头读到尾"、封面在不在
盘上）从没被一次真请求穿过。真后端 e2e 里浏览器确实在放片子，那是**另一个进程**，
不进这份读数。

对象存储那两格要真桶才红得起来，这里用 moto 在进程内接住 botocore：它证明的是
**接线正确**（地址决定读法、区间原样交给存储层、读不到不等于空库），不证明真 MinIO
对同一个请求回一模一样的头——那一层仍是手工核对，同 `tests/test_storage/
test_s3_storage.py` 的说明。
"""

import pytest

# boto3/moto 属于可选依赖：没装 .[s3] 的人不该在跑测试时先撞一次整文件报错。
_reason = '对象存储用例需要额外依赖：pip install -e ".[dev,s3]"'
pytest.importorskip("boto3", reason=_reason)
pytest.importorskip("moto", reason=_reason)

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from src.config import settings  # noqa: E402
from src.models.source import VideoSource  # noqa: E402
from src.models.video import Video  # noqa: E402

BUCKET = "media"
OBJ_KEY = "shows/01.mkv"
LOCATOR = f"s3://{BUCKET}/{OBJ_KEY}"
BODY = bytes(range(256)) * 40


async def _video(db_session, **fields) -> Video:
    source = VideoSource(
        name=fields.pop("source_name", "盘"),
        path=fields.pop("source_path", "./data/videos"),
        type=fields.pop("source_type", "local"),
    )
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, **fields)
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


@pytest.fixture
def bucket_credentials(monkeypatch):
    """凭证只对着 moto 有意义；刻意与 test_s3_storage 那组不同名，
    这样客户端缓存（按配置取键）一定会在我们的 mock 里重建一次。
    """
    monkeypatch.setattr(settings, "s3_access_key_id", "stream-access-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "stream-secret-key")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_addressing_style", "auto")


def _seed(keys: tuple[str, ...]) -> None:
    client = boto3.client("s3", region_name=settings.s3_region)
    client.create_bucket(Bucket=BUCKET)
    for key in keys:
        client.put_object(Bucket=BUCKET, Key=key, Body=BODY)


async def test_a_local_video_is_handed_to_a_file_response(client, db_session, tmp_path):
    """整文件、本地：路由把路径原样交给 FileResponse，长度由文件本身说了算。"""
    path = tmp_path / "01.mkv"
    path.write_bytes(BODY)
    video = await _video(
        db_session,
        filepath=str(path),
        title="01",
        format="mkv",
        file_size=1,  # 表里那一格是陈的：播放不能按它来报长度
    )

    response = await client.get(f"/api/videos/{video.id}/stream")

    assert response.status_code == 200
    assert response.content == BODY
    assert response.headers["content-type"] == "video/x-matroska"
    assert response.headers["content-length"] == str(len(BODY))
    assert response.headers["accept-ranges"] == "bytes"
    assert 'filename="01.mkv"' in response.headers["content-disposition"]


async def test_a_local_range_request_is_answered_from_the_endpoint(
    client, db_session, tmp_path
):
    """播放器拖进度条打的是这条地址，不是 `_handle_range_request` 那个函数。"""
    path = tmp_path / "02.mp4"
    path.write_bytes(BODY)
    video = await _video(
        db_session, filepath=str(path), title="02", format="mp4", file_size=len(BODY)
    )

    response = await client.get(
        f"/api/videos/{video.id}/stream", headers={"Range": "bytes=100-199"}
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 100-199/{len(BODY)}"
    assert response.content == BODY[100:200]


@pytest.mark.parametrize(
    "extension,expected",
    [
        (".mp4", "video/mp4"),
        (".m4v", "video/mp4"),
        (".webm", "video/webm"),
        (".mkv", "video/x-matroska"),
        (".avi", "video/x-msvideo"),
        (".mov", "video/quicktime"),
        (".flv", "video/x-flv"),
        (".wmv", "video/x-ms-wmv"),
        (".MKV", "video/x-matroska"),
        (".mpeg", "video/mp4"),
    ],
)
async def test_the_offered_media_type_follows_the_suffix(
    extension, expected, client, db_session, tmp_path
):
    """这张表整个钉住，含"表里没有"那一格。

    报错 content-type 不是难看一点，是某些浏览器直接不放：所以八个已知后缀和
    兜底那一格都得有人签，只签一格的话剩下七行改错了没人红。
    """
    path = tmp_path / f"03{extension}"
    path.write_bytes(BODY)
    video = await _video(
        db_session, filepath=str(path), title="03", format="mp4", file_size=len(BODY)
    )

    response = await client.get(f"/api/videos/{video.id}/stream")

    assert response.headers["content-type"] == expected


async def test_streaming_a_video_that_is_not_in_the_library_is_404(client, db_session):
    """这条不能走到"读不到"的占位：占位是给文件的问题，不是给不存在的行的。"""
    response = await client.get("/api/videos/4242/stream")

    assert response.status_code == 404


async def test_a_whole_object_is_read_out_of_the_bucket(client, db_session, bucket_credentials):
    """对象存储没有本地文件，整文件就是"从头读到尾的那一段"——这条分支此前没人请求过。"""
    video = await _video(
        db_session,
        source_name="桶",
        source_path=f"s3://{BUCKET}/shows",
        source_type="minio",
        filepath=LOCATOR,
        title="01",
        format="mkv",
        file_size=len(BODY),
    )

    with mock_aws():
        _seed((OBJ_KEY,))
        response = await client.get(f"/api/videos/{video.id}/stream")

    assert response.status_code == 200
    assert response.content == BODY
    assert response.headers["content-length"] == str(len(BODY))
    assert response.headers["content-type"] == "video/x-matroska"
    assert response.headers["accept-ranges"] == "bytes"


async def test_an_object_range_request_is_read_out_of_the_bucket(
    client, db_session, bucket_credentials
):
    """分段那一路的取字节是在响应里现挑存储的：地址决定读法，不是路由决定。"""
    video = await _video(
        db_session,
        source_name="桶",
        source_path=f"s3://{BUCKET}/shows",
        source_type="minio",
        filepath=LOCATOR,
        title="01",
        format="mkv",
        file_size=len(BODY),
    )

    with mock_aws():
        _seed((OBJ_KEY,))
        response = await client.get(
            f"/api/videos/{video.id}/stream", headers={"Range": "bytes=512-1023"}
        )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 512-1023/{len(BODY)}"
    assert response.content == BODY[512:1024]


async def test_an_object_gone_from_the_bucket_falls_back_without_500(
    client, db_session, bucket_credentials
):
    """凭证是好的、桶也在，只是那把键没了——和"没配凭证"走的是同一个占位。

    `test_storage_gates.py` 那条测的是够不着桶；这一条钉的是桶答了但没这个对象，
    少一个字节都不能把播放器打成 500。
    """
    video = await _video(
        db_session,
        source_name="桶",
        source_path=f"s3://{BUCKET}/shows",
        source_type="minio",
        filepath=LOCATOR,
        title="01",
        format="mkv",
        file_size=len(BODY),
    )

    with mock_aws():
        _seed(("shows/another.mkv",))
        response = await client.get(f"/api/videos/{video.id}/stream")

    assert response.status_code == 200
    assert "note" in response.json()


async def test_a_cover_on_disk_is_served_as_a_jpeg(client, db_session, tmp_path):
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    video = await _video(
        db_session,
        filepath=str(tmp_path / "04.mkv"),
        title="04",
        format="mkv",
        file_size=len(BODY),
        thumbnail_path=str(cover),
    )

    response = await client.get(f"/api/videos/{video.id}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8\xff\xe0jpeg"


async def test_a_cover_that_moved_away_says_so_instead_of_500(client, db_session, tmp_path):
    """行还在、封面文件不在了：这只能是"没有封面"，不能是一个 500。"""
    video = await _video(
        db_session,
        filepath=str(tmp_path / "05.mkv"),
        title="05",
        format="mkv",
        file_size=len(BODY),
        thumbnail_path=str(tmp_path / "gone.jpg"),
    )

    response = await client.get(f"/api/videos/{video.id}/thumbnail")

    assert response.status_code == 200
    assert response.json() == {"thumbnail": None, "message": "No thumbnail available"}


async def test_a_cover_of_a_video_that_is_not_in_the_library_is_404(client, db_session):
    response = await client.get("/api/videos/4242/thumbnail")

    assert response.status_code == 404
