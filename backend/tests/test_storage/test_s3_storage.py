"""The S3 storage, tested against an in-memory bucket.

moto intercepts botocore in-process, so these tests need no network and no
MinIO instance -- but that also means they prove the client is *wired* right,
not that a real server answers the same way. Endpoint behaviour beyond the S3
API contract is still a manual check.
"""
import pytest

# boto3/moto 属于可选依赖：没装 .[s3] 的人不该在跑测试时先撞一次整文件报错。
_reason = '对象存储用例需要额外依赖：pip install -e ".[dev,s3]"'
pytest.importorskip("boto3", reason=_reason)
pytest.importorskip("moto", reason=_reason)

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from src.config import settings
from src.storage import S3MediaStorage, UnsupportedStorage, storage_for_source
from src.storage.s3 import split_locator, split_root
from src.utils.file_fingerprint import edge_fingerprint, hash_edges

BUCKET = "media"
BODY = bytes(range(256)) * 40


@pytest.fixture
def credentials(monkeypatch):
    """凭证只对着 moto 有意义；留空即"未配置"，那是另一批用例。"""
    monkeypatch.setattr(settings, "s3_access_key_id", "test-access-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret-key")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_addressing_style", "auto")


def _seed(files: dict[str, bytes]) -> None:
    client = boto3.client("s3", region_name=settings.s3_region)
    client.create_bucket(Bucket=BUCKET)
    for key, body in files.items():
        client.put_object(Bucket=BUCKET, Key=key, Body=body)


def test_lists_only_videos_under_the_prefix(credentials):
    with mock_aws():
        _seed(
            {
                "shows/01.mkv": BODY,
                "shows/01.srt": b"subtitle",
                "shows-extra/02.mkv": b"other series",
                "loose.mp4": BODY,
            }
        )

        found = S3MediaStorage().list_videos(f"s3://{BUCKET}/shows")

    assert [item.locator for item in found] == [f"s3://{BUCKET}/shows/01.mkv"]
    assert found[0].filename == "01.mkv"
    assert found[0].extension == ".mkv"
    assert found[0].size == len(BODY)


def test_a_bare_bucket_lists_everything_in_it(credentials):
    with mock_aws():
        _seed({"shows/01.mkv": BODY, "movies/film.mp4": BODY})
        found = S3MediaStorage().list_videos(f"s3://{BUCKET}")
    assert sorted(item.locator for item in found) == [
        f"s3://{BUCKET}/movies/film.mp4",
        f"s3://{BUCKET}/shows/01.mkv",
    ]


def test_size_and_existence(credentials):
    with mock_aws():
        _seed({"shows/01.mkv": BODY})
        storage = S3MediaStorage()
        locator = f"s3://{BUCKET}/shows/01.mkv"

        assert storage.size(locator) == len(BODY)
        assert storage.exists(locator) is True
        assert storage.size(f"s3://{BUCKET}/shows/gone.mkv") is None
        assert storage.exists(f"s3://{BUCKET}/shows/gone.mkv") is False


def test_range_reads_the_requested_slice_inclusive(credentials):
    with mock_aws():
        _seed({"shows/01.mkv": BODY})
        streamed = b"".join(
            S3MediaStorage().iter_range(f"s3://{BUCKET}/shows/01.mkv", 100, 199)
        )

    assert streamed == BODY[100:200]


def test_fingerprint_matches_what_the_local_disk_would_report(credentials, tmp_path):
    """同一个文件放进桶里和留在盘上，指纹必须一模一样。

    重复检测是跨源比对的，两边算法不同就等于悄悄停止匹配。
    """
    with mock_aws():
        _seed({"shows/01.mkv": BODY})
        on_bucket = S3MediaStorage().edge_fingerprint(f"s3://{BUCKET}/shows/01.mkv")

    on_disk = tmp_path / "01.mkv"
    on_disk.write_bytes(BODY)
    assert on_bucket == edge_fingerprint(str(on_disk))
    assert on_bucket == hash_edges(BODY[: 1024 * 1024], BODY[-1024 * 1024:])


def test_unreachable_bucket_is_not_reported_as_empty(credentials):
    with mock_aws():
        _seed({"shows/01.mkv": BODY})

        assert S3MediaStorage().reachable(f"s3://{BUCKET}/shows") is True
        assert S3MediaStorage().reachable("s3://no-such-bucket") is False


def test_missing_credentials_are_unreachable_not_an_error():
    """没配凭证要说"这个源够不着"，不能读成"桶是空的"。"""
    storage = storage_for_source("minio")

    assert storage.reachable("s3://anything") is False

    with pytest.raises(UnsupportedStorage, match="S3_ACCESS_KEY_ID"):
        storage.list_videos("s3://anything")


@pytest.mark.parametrize(
    "root",
    ["s3://", "s3:///prefix"],
)
def test_a_root_without_a_bucket_is_rejected(root):
    with pytest.raises(UnsupportedStorage, match="bucket"):
        split_root(root)


def test_a_locator_without_a_key_is_rejected():
    with pytest.raises(UnsupportedStorage):
        split_locator(f"s3://{BUCKET}")
