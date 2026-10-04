# tests/test_backup.py
"""备份核心的底线：口令不外泄、读不回来的文件不算备份、轮转只碰自己的文件、非 PG 直接拒。

``is_stale`` 守的是另一头：多久没有 dump 就算这个库失去了保险，启动时该补一趟。
子进程全部由 ``_run`` 这一个口子出去，用例替它演一套 pg_dump/pg_restore：
断言的是**真实调用出去的 argv 和环境变量**，因为「口令有没有进命令行」这件事
只有在这里能被锁住——真跑一次 pg_dump 反而看不出来。
"""

import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from src import backup
from src.backup import (
    BackupError,
    is_postgres,
    is_stale,
    latest_backup,
    parse_target,
    parse_time_of_day,
    pg_binary,
    prune,
    run_backup,
)

#: 带口令、带百分号转义、带非默认端口的完整形态，转义必须在这一层解回来。
PG_URL = "postgresql+asyncpg://home%2Fsites_app:S3cr%2533t@db.internal:6543/home_sites"
PASSWORD = "S3cr%33t"
NOW = datetime(2026, 10, 4, 3, 30, 0, tzinfo=timezone.utc)


class FakeClient:
    """演 pg_dump / pg_restore：记录每次调用，按开关决定成功还是失败。"""

    def __init__(
        self,
        *,
        dump_rc: int = 0,
        list_rc: int = 0,
        dump_bytes: bytes = b"PGDMP\x00fake",
    ) -> None:
        self.dump_rc = dump_rc
        self.list_rc = list_rc
        self.dump_bytes = dump_bytes
        self.calls: list[tuple[list[str], dict[str, str], int]] = []

    def __call__(
        self, cmd: list[str], env: dict[str, str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((cmd, env, timeout))
        if "pg_dump" in os.path.basename(cmd[0]):
            if self.dump_rc != 0:
                return subprocess.CompletedProcess(cmd, self.dump_rc, "", "pg_dump: 连接被拒绝")
            with open(cmd[cmd.index("-f") + 1], "wb") as handle:
                handle.write(self.dump_bytes)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(
            cmd, self.list_rc, "; archive 内容清单", "pg_restore: 不是有效的归档"
        )

    def cmd_for(self, tool: str) -> list[str]:
        return next(cmd for cmd, _env, _t in self.calls if tool in os.path.basename(cmd[0]))

    @property
    def dump_cmd(self) -> list[str]:
        return self.cmd_for("pg_dump")

    @property
    def list_cmd(self) -> list[str]:
        return self.cmd_for("pg_restore")

    @property
    def env(self) -> dict[str, str]:
        return self.calls[0][1]


@pytest.fixture
def client(monkeypatch):
    """把 pg_dump/pg_restore 换成 :class:`FakeClient`，并假定二进制都找得到。"""
    fake = FakeClient()
    monkeypatch.setattr(backup, "_run", fake)
    monkeypatch.setattr(backup, "pg_binary", lambda name, bindir="": f"/opt/pgsql/bin/{name}")
    return fake


def test_password_only_travels_in_the_child_environment(client, tmp_path):
    """口令只进子进程的 PGPASSWORD，argv 里一个字都不该出现。"""
    out = run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    assert len(client.calls) == 2
    for cmd, _env, _timeout in client.calls:
        assert not any(PASSWORD in arg for arg in cmd), cmd
    assert client.env["PGPASSWORD"] == PASSWORD
    # 整套环境都得带上，否则 Windows 上的子进程连系统目录都找不到。
    assert client.env.get("PATH") == os.environ.get("PATH")
    assert os.path.isfile(out)


def test_dump_connects_to_the_url_it_was_given(client, tmp_path):
    """URL 的每个部分都得原样落到 pg_dump 的参数上，转义要解回来。"""
    run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    cmd = client.dump_cmd
    assert cmd[cmd.index("-h") + 1] == "db.internal"
    assert cmd[cmd.index("-p") + 1] == "6543"
    assert cmd[cmd.index("-U") + 1] == "home/sites_app"
    assert cmd[cmd.index("-d") + 1] == "home_sites"
    assert "-Fc" in cmd and "--no-owner" in cmd


def test_dump_name_carries_the_utc_second(client, tmp_path):
    """同一天的多次运行不能互相覆盖，文件名按 UTC 到秒。"""
    out = run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    assert os.path.basename(out) == "home_sites_20261004T033000Z.dump"
    assert os.path.dirname(out) == os.path.abspath(str(tmp_path))


def test_a_dump_that_cannot_be_read_back_is_not_left_behind(client, tmp_path):
    """pg_restore -l 读不回来就是废纸，留在目录里只会变成假的安全感。"""
    client.list_rc = 1

    with pytest.raises(BackupError, match="读不回来"):
        run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    assert os.listdir(tmp_path) == []


def test_a_zero_byte_dump_is_a_failure_even_when_pg_dump_exits_zero(client, tmp_path):
    """退出码 0 但没写出内容（磁盘满、写到一半被杀）同样不能算备份完成。"""
    client.dump_bytes = b""

    with pytest.raises(BackupError, match="没写出任何内容"):
        run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    assert os.listdir(tmp_path) == []


def test_pg_dump_failing_reports_the_server_reason(client, tmp_path):
    """失败原因要能把 pg_dump 的话带出来，通知里才有的可看。"""
    client.dump_rc = 2

    with pytest.raises(BackupError, match="连接被拒绝"):
        run_backup(database_url=PG_URL, backup_dir=str(tmp_path), now=NOW)

    assert os.listdir(tmp_path) == []


def test_rotation_keeps_recent_dumps_and_touches_nothing_else(tmp_path):
    """轮转只删本模块那种带 UTC 时间戳的名字；手工快照再像也不碰。

    两个"必须活着"的名字是从真机 ``data/pg-backups`` 抄来的：手工命名同样以
    ``home_sites_`` 开头、同样以 ``.dump`` 结尾，只看前缀后缀就会把某次改动
    唯一的现场备份当成过期文件清掉。
    """
    old = tmp_path / "home_sites_20260901T033000Z.dump"
    fresh = tmp_path / "home_sites_20261003T033000Z.dump"
    manual = tmp_path / "home_sites_post_account_cleanup_20261004_154215.dump"
    pre_change = tmp_path / "home_sites-before-notification-cleanup-20261004-165507.dump"
    notes = tmp_path / "notes.txt"
    for path in (old, fresh, manual, pre_change, notes):
        path.write_bytes(b"x")
    _set_age(old, days=30)
    _set_age(fresh, days=1)
    _set_age(manual, days=30)
    _set_age(pre_change, days=30)

    removed = prune(backup_dir=str(tmp_path), keep_days=7, now=NOW)

    assert [os.path.basename(path) for path in removed] == [old.name]
    assert {p.name for p in tmp_path.iterdir()} == {
        fresh.name,
        manual.name,
        pre_change.name,
        notes.name,
    }


def test_turning_rotation_off_keeps_the_whole_history(tmp_path):
    """keep_days<=0 是"不轮转"，不是"下一次运行把历史全清掉"。"""
    ancient = tmp_path / "home_sites_20200101T000000Z.dump"
    ancient.write_bytes(b"x")
    _set_age(ancient, days=999)

    assert prune(backup_dir=str(tmp_path), keep_days=0, now=NOW) == []
    assert ancient.exists()


def test_latest_backup_answers_whether_the_database_is_still_insured(tmp_path):
    """成功不吭声，所以"最近一次备份"得有个不用翻目录就能问的出处。"""
    assert latest_backup(str(tmp_path / "missing")) is None

    older = tmp_path / "home_sites_20261001T033000Z.dump"
    newer = tmp_path / "home_sites_20261003T033000Z.dump"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    _set_age(older, days=2)
    _set_age(newer, days=1)
    (tmp_path / "readme.md").write_text("不算备份")

    assert latest_backup(str(tmp_path)) == str(newer)


def test_sqlite_is_refused_before_anything_runs(client, tmp_path):
    """SQLite 没有 pg_dump 可跑：早点拒绝，别让定时任务每晚写一条失败通知。"""
    target = tmp_path / "backups"
    assert is_postgres("sqlite+aiosqlite:///./data/videos.db") is False
    assert is_postgres(PG_URL) is True

    with pytest.raises(BackupError, match="PostgreSQL"):
        run_backup(database_url="sqlite+aiosqlite:///./data/videos.db", backup_dir=str(target))

    assert not target.exists()
    assert client.calls == []


def test_missing_binary_says_where_to_point_it(tmp_path, monkeypatch):
    """找不到 pg_dump 时，错误里要直接给出解决办法（PG_BINDIR）。"""
    monkeypatch.setattr(backup.shutil, "which", lambda _name: None)

    with pytest.raises(BackupError, match="PG_BINDIR"):
        run_backup(database_url=PG_URL, backup_dir=str(tmp_path))


def test_pg_bindir_is_used_verbatim_when_given(tmp_path, monkeypatch):
    """Windows 上盘上是 pg_dump.exe，调用方只会说 pg_dump，后缀得自己补。"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    dumper = bindir / ("pg_dump.exe" if os.name == "nt" else "pg_dump")
    dumper.write_bytes(b"x")
    monkeypatch.setattr(backup.shutil, "which", lambda _name: None)

    assert pg_binary("pg_dump", str(bindir)) == str(dumper)


def test_path_lookup_is_the_fallback_when_no_bindir_is_set(monkeypatch):
    """留空 PG_BINDIR 就是按 PATH 找，找到什么用什么。"""
    monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert pg_binary("pg_restore") == "/usr/bin/pg_restore"


def test_time_of_day_accepts_only_a_real_clock():
    assert parse_time_of_day("03:30") == (3, 30)
    assert parse_time_of_day("23:59") == (23, 59)

    for bad in ("", "3:5", "24:00", "03:60", "0b:00", "03:30:00"):
        with pytest.raises(BackupError):
            parse_time_of_day(bad)


def test_target_requires_a_host_and_a_database():
    with pytest.raises(BackupError, match="主机名或库名"):
        parse_target("postgresql+asyncpg://user@/dbname")
    with pytest.raises(BackupError, match="主机名或库名"):
        parse_target("postgresql+asyncpg://user:pw@host")


def test_password_is_left_out_of_the_repr():
    """日志里把这个对象打出来是常事，口令不能跟着出去。"""
    assert PASSWORD not in repr(parse_target(PG_URL))


def test_the_database_is_insured_until_the_nightly_window_passes(tmp_path):
    """``is_stale`` 的线要落在"一夜加一段缓冲"之外，否则每晚的健康备份都会被当成出事。"""
    dump = tmp_path / "home_sites_20261004T033000Z.dump"
    dump.write_bytes(b"x")

    # 03:30 备份成功，04:00 起来问一遍：不陈旧。
    _set_age_hours(dump, 0.5)
    assert is_stale(str(tmp_path), now=NOW) is False

    # 同一份文件，25 小时后（当晚那一趟没跑成）还不算——留的是一整夜的重试余量。
    _set_age_hours(dump, 25)
    assert is_stale(str(tmp_path), now=NOW) is False

    # 越过 36 小时：连续两晚没有了，这才是"保不住了"。
    _set_age_hours(dump, 37)
    assert is_stale(str(tmp_path), now=NOW) is True


def test_no_dump_at_all_is_stale(tmp_path):
    """空目录和缺目录都算陈旧——第一次启动就该补一趟，而不是等第一个 03:30。"""
    assert is_stale(str(tmp_path), now=NOW) is True
    assert is_stale(str(tmp_path / "还没建"), now=NOW) is True

    (tmp_path / "home_sites_manual_before_cleanup.dump").write_bytes(b"x")
    # 手工快照不参与判断，和轮转"只认自己写出来的那个名字"是同一条规矩。
    assert is_stale(str(tmp_path), now=NOW) is True


def _set_age(path, days: int) -> None:
    when = (NOW - timedelta(days=days)).timestamp()
    os.utime(path, (when, when))


def _set_age_hours(path, hours: float) -> None:
    when = (NOW - timedelta(hours=hours)).timestamp()
    os.utime(path, (when, when))
