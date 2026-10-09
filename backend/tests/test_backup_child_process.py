# tests/test_backup_child_process.py
"""备份那四格薄位置的补票：`_run` 第一次真的起一个进程，三道兜底分支第一次被走到（#174）。

`src/backup.py` 此前是 95%，缺的正好是四类各一：`124`（`_run` 里那句真的
`subprocess.run`）、`152`（`BACKUP_DIR` 是空的那道闸门）、`217-218`（轮转遇到 stat 不出的条目
就跳过）、`266-267`（陈旧判断遇到 stat 不出的文件算陈旧）。前三格之所以是盲区，原因各不相同：
`tests/test_backup.py` 把 `_run` 整个换成替身（那是对的——"口令有没有进 argv"只有在那一头才钉得住，
真跑一次 pg_dump 反而看不出来），代价是**发出去的 argv、环境变量、超时和那套解码参数本身没有一格的
签字**；`152` 那一格今天从没有调用方给过空串；后两格要有"目录里列得出、stat 不出"的条目才走得到。

这里补的是**另一头**：真的起一个真子进程（用 `sys.executable`，不依赖 pg_dump 在不在 PATH 上），
以及真把 `os.path.getmtime` 抛一次。探针量出来的那条更要紧：`is_stale` 的 docstring 明写
"stat 不出的条目按陈旧处理而不是抛异常，因为它跑在启动那一段，一个悬空条目不该把应用带下去"，
而实测**只有晚一步消失的文件才走得到那句 `return True`**——如果它在 `latest_backup` 挑最新那一份
之前就已经 stat 不出，异常是从 `261` 那行外抛的，`264-267` 那个 `try` 包不住。改成包不住就是行为
变更，已记入待用户定夺；下面的用例钉的是**现状**。
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from src import backup
from src.backup import BackupError

#: 哨兵值只在这条测试的父进程和它的子进程之间走，不是任何真口令。
SENTINEL_KEY = "BACKUP_CHILD_SENTINEL"
SENTINEL_VALUE = "child-only-value"
NOW = datetime(2026, 10, 4, 3, 30, 0, tzinfo=timezone.utc)
GHOST = "home_sites_20200101T000000Z.dump"
#: 编出来的地址，只为过了 `parse_target` 那道方言闸门；里面的口令是假值。
GATE_URL = "postgresql+asyncpg://gate_app:not-a-password@db.internal:5432/home_sites"


def _child(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.pop(SENTINEL_KEY, None)
    env.update(extra)
    return env


def _listdir(monkeypatch, names: list[str]) -> None:
    """只换目录清单，`getmtime` 保持是真的——它会对不在盘上的名字真抛一次。"""
    monkeypatch.setattr(backup.os, "listdir", lambda _dir: sorted(names))


# ---------- 124：_run 真的起进程 ----------


def test_the_childs_own_streams_are_captured_as_text_with_its_exit_code():
    result = backup._run(
        _child("import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"),
        _env(),
        30,
    )

    assert result.returncode == 3
    assert isinstance(result.stdout, str) and isinstance(result.stderr, str)
    assert (result.stdout.strip(), result.stderr.strip()) == ("out", "err")


def test_a_utf8_diagnostic_from_the_child_arrives_whatever_this_machines_codepage_is():
    """`encoding="utf-8"` 是实参不是装饰：这台机器的控制台代码页是 cp936。

    子进程把 UTF-8 字节直接写进二进制流，父进程要是按本地代码页解，pg_dump 那句中文诊断就会
    变成一串谁也读不懂的字节——而那句是失败通知里唯一的原因。
    """
    result = backup._run(
        _child(
            "import sys; sys.stderr.buffer.write("
            "'片名里的中文在 cp936 控制台上会被解错'.encode('utf-8')); sys.stderr.flush()"
        ),
        _env(),
        30,
    )

    assert result.stderr == "片名里的中文在 cp936 控制台上会被解错"


def test_bytes_the_child_cannot_be_decoded_as_are_replaced_instead_of_raising():
    """`errors="replace"` 承的重：换掉它，一句带坏字节的诊断会把整个备份任务炸成
    UnicodeDecodeError——那时失败通知里连原因都不会有。
    """
    result = backup._run(
        _child("import sys; sys.stdout.buffer.write(bytes([255, 254])); sys.stdout.flush()"),
        _env(),
        30,
    )

    assert result.stdout.count(chr(0xFFFD)) == 2


def test_the_timeout_is_forwarded_to_the_child_and_comes_back_as_an_error():
    """超时是 `_run` 唯一的"子进程卡住"出口：pg_dump 挂住时任务必须有话可说。"""
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        backup._run(_child("import time; time.sleep(30)"), _env(), 1)

    assert caught.value.timeout == 1


def test_the_environment_is_handed_to_the_child_verbatim_and_nothing_more(monkeypatch):
    """`_run` 用的是**交给它的那一份**环境，不是父进程那一份。

    这一条比"值能进去"更值钱：`run_backup` 是按 `env = {**os.environ}` 现抄一份再往上加
    `PGPASSWORD` 的，所以 `_run` 若改成回落到父进程环境（`env=None`）或被两边合并，口令就再也
    清不掉——传进去一份"没有它"的环境也没用。子进程按两种偏差各回一个不同的退出码。
    """
    parent_only = SENTINEL_KEY + "_PARENT_ONLY"
    monkeypatch.setenv(parent_only, "only-in-the-parent")
    code = (
        "import os,sys;"
        "sys.exit(5 if os.environ.get('"
        + SENTINEL_KEY
        + "') != '"
        + SENTINEL_VALUE
        + "' else 6 if '"
        + parent_only
        + "' in os.environ else 0)"
    )
    child_env = {k: v for k, v in os.environ.items() if k != parent_only}
    child_env[SENTINEL_KEY] = SENTINEL_VALUE

    assert backup._run(_child(code), child_env, 30).returncode == 0
    assert backup._run(_child(code), {**child_env, SENTINEL_KEY: "wrong"}, 30).returncode == 5


# ---------- 152：空目录那道闸门 ----------


def test_an_empty_backup_dir_is_refused_before_anything_is_created(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        backup,
        "_run",
        lambda cmd, env, timeout: calls.append(cmd)
        or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setattr(backup, "pg_binary", lambda name, bindir="": name)

    with pytest.raises(BackupError, match="没处可写"):
        backup.run_backup(database_url=GATE_URL, backup_dir="", now=NOW)

    assert calls == []
    assert os.listdir(str(tmp_path)) == []


# ---------- 217-218 / 266-267：stat 不出的条目 ----------


def test_rotation_skips_an_entry_it_cannot_stat_and_still_clears_the_old_ones(
    tmp_path, monkeypatch
):
    """一个列得出、stat 不出的名字不能把整轮轮转带停——旁边那份真过期的还得清掉。"""
    old = tmp_path / "home_sites_20260901T033000Z.dump"
    old.write_bytes(b"x")
    when = (NOW - timedelta(days=30)).timestamp()
    os.utime(old, (when, when))
    _listdir(monkeypatch, [GHOST, old.name])

    removed = backup.prune(backup_dir=str(tmp_path), keep_days=7, now=NOW)

    assert [os.path.basename(path) for path in removed] == [old.name]
    assert not old.exists()


def test_a_dump_that_vanishes_between_the_listing_and_the_stat_counts_as_stale(
    tmp_path, monkeypatch
):
    """`266-267`：挑完最新那一份之后它才消失（夜间轮转、手工删、杀软挪走）算陈旧，不抛。"""
    monkeypatch.setattr(
        backup, "latest_backup", lambda _dir: str(tmp_path / GHOST)
    )

    assert backup.is_stale(str(tmp_path), now=NOW) is True


def test_an_entry_that_was_already_gone_before_the_listing_gets_out_as_an_error(
    tmp_path, monkeypatch
):
    """本单量出的那个洞（钉的是现状，不是认可）：异常从 `261` 外抛，`try` 包不住。

    `is_stale` 的 docstring 承诺 stat 不出的条目按陈旧处理，而 `latest_backup` 自己就要
    `max(key=getmtime)`——同一个 OSError 早一步发生就穿出去。调用方
    `scheduler/tasks.py:93` 那句 `if not backup.is_stale(...)` 没有任何 `try` 包着，
    于是补跑任务在还没开始备份之前就死掉：库从此没有保险，也没有一条通知说得清为什么。
    """
    _listdir(monkeypatch, [GHOST])

    with pytest.raises(FileNotFoundError):
        backup.is_stale(str(tmp_path), now=NOW)
