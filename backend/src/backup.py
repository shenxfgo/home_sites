"""PostgreSQL backups: one pg_dump, verified before it is trusted, then rotated.

A backup you never read back is a file, not a backup, so every dump goes through
``pg_restore -l`` and a dump that fails that check is deleted instead of being
kept around as a false sense of safety. The password only ever travels through
the child process's environment — never argv, where ``tasklist``/``ps`` would
show it, and never a log line.

SQLite is not supported here: the whole point is a real ``pg_dump`` against the
live database, and the caller decides whether to arm the job at all via
:func:`is_postgres`.
"""

import contextlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

#: 备份文件名前缀。
FILE_PREFIX = "home_sites_"
DUMP_SUFFIX = ".dump"

#: 轮转认领文件的唯一依据：只删本模块写出来的那个名字（UTC 时间戳到秒）。
#: 光看前缀不够——目录里本来就有手工快照叫
#: ``home_sites_post_account_cleanup_20261004_154215.dump``，按前缀认亲它就会
#: 在一周后被"轮转"掉，而那是某次改动唯一的现场备份。
_DUMP_NAME = re.compile(r"home_sites_\d{8}T\d{6}Z\.dump")

_DUMP_TIMEOUT_SECONDS = 600
_LIST_TIMEOUT_SECONDS = 60


class BackupError(RuntimeError):
    """Raised when a backup could not be produced or is not restorable."""


@dataclass(frozen=True)
class PgTarget:
    """Where to dump from. ``password`` stays out of ``repr`` on purpose."""

    host: str
    port: int
    user: str
    dbname: str
    password: str = field(repr=False, default="")


def is_postgres(database_url: str) -> bool:
    """True when this URL points at PostgreSQL, i.e. when a backup can work."""
    return urlsplit(database_url).scheme.startswith("postgresql")


def parse_target(database_url: str) -> PgTarget:
    """Split a SQLAlchemy PG URL into pg_dump connection parts.

    The URL carries the app-role password (``postgresql+asyncpg://user:pw@host``),
    so the returned object holds it in memory only; nothing here puts it into a
    command line.
    """
    parts = urlsplit(database_url)
    if not is_postgres(database_url):
        raise BackupError(f"只备份 PostgreSQL，当前是 {parts.scheme or '未知方言'}")
    if not parts.hostname or not parts.path.strip("/"):
        raise BackupError("DATABASE_URL 缺少主机名或库名，没法确定备份目标")
    return PgTarget(
        host=parts.hostname,
        port=parts.port or 5432,
        user=unquote(parts.username or ""),
        dbname=unquote(parts.path.strip("/")),
        password=unquote(parts.password or ""),
    )


def parse_time_of_day(value: str) -> tuple[int, int]:
    """``"03:30"`` -> ``(3, 30)``. Raises on anything else."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise BackupError(f"BACKUP_TIME 需要 HH:MM 的 24 小时制时刻，收到的是 {value!r}")
    return int(match.group(1)), int(match.group(2))


def pg_binary(name: str, bindir: str = "") -> str:
    """Locate a PostgreSQL client binary.

    With ``bindir`` set (typical on Windows, where the server's ``bin`` is not on
    ``PATH``) look inside it directly — and try ``.exe`` too, because the file on
    disk is ``pg_dump.exe`` while every caller says ``pg_dump``. Otherwise fall
    back to ``PATH``. Fail early and loudly: a missing ``pg_dump`` discovered at
    3:30 by nobody is not a failure anyone would call a backup.
    """
    if bindir:
        stem = os.path.join(bindir, name)
        candidates = [stem, f"{stem}.exe"] if os.name == "nt" else [stem]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    else:
        found = shutil.which(name)
        if found:
            return found

    raise BackupError(
        f"找不到 {name}（设置 PG_BINDIR 指向 PostgreSQL 的 bin 目录，或把它加进 PATH）"
    )


def _dump_name(now: datetime) -> str:
    return f"{FILE_PREFIX}{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}{DUMP_SUFFIX}"


def _is_dump(name: str) -> bool:
    return bool(_DUMP_NAME.fullmatch(name))


def _run(cmd: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    """One child process. Standalone so a test can watch the argv and the env."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def run_backup(
    *,
    database_url: str,
    backup_dir: str,
    keep_days: int = 7,
    pg_bindir: str = "",
    now: datetime | None = None,
) -> str:
    """Dump the database into ``backup_dir``, verify it, prune the old ones.

    Returns the absolute path of the dump. Raises :class:`BackupError` for
    anything that means the result cannot be trusted — including a dump that
    ``pg_restore -l`` refuses to read, in which case the broken file is removed
    so the directory only ever holds restorable backups.
    """
    target = parse_target(database_url)
    if not backup_dir:
        raise BackupError("BACKUP_DIR 是空的，没处可写")

    stamp = now or datetime.now(timezone.utc)
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(os.path.abspath(backup_dir), _dump_name(stamp))

    dumper = pg_binary("pg_dump", pg_bindir)
    lister = pg_binary("pg_restore", pg_bindir)

    # PGPASSWORD goes in the child's environment only. argv would make it
    # visible to any process listing on the machine.
    env = {**os.environ}
    if target.password:
        env["PGPASSWORD"] = target.password

    dump_cmd = [
        dumper,
        "-h", target.host,
        "-p", str(target.port),
        "-U", target.user,
        "-d", target.dbname,
        "-Fc",
        "--no-owner",
        "-f", path,
    ]
    result = _run(dump_cmd, env, _DUMP_TIMEOUT_SECONDS)
    if result.returncode != 0:
        _discard(path)
        reason = (result.stderr or result.stdout).strip()[:400]
        raise BackupError(f"pg_dump 失败（退出码 {result.returncode}）: {reason}")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        _discard(path)
        raise BackupError("pg_dump 说成功了，但没写出任何内容")

    # Read the TOC back: proves the file is a dump and not a truncated write.
    listing = _run([lister, "-l", path], env, _LIST_TIMEOUT_SECONDS)
    if listing.returncode != 0:
        _discard(path)
        raise BackupError(
            f"备份读不回来（pg_restore -l 退出码 {listing.returncode}）: "
            f"{(listing.stderr or listing.stdout).strip()[:400]}"
        )

    logger.info("已备份 %s 到 %s", target.dbname, path)
    prune(backup_dir=backup_dir, keep_days=keep_days, now=stamp)
    return path


def prune(*, backup_dir: str, keep_days: int, now: datetime | None = None) -> list[str]:
    """Delete our own dumps older than ``keep_days``; return what went away.

    ``keep_days <= 0`` turns pruning off rather than wiping the whole history —
    disabling rotation shouldn't be a way to lose every backup on the next run.
    """
    if keep_days <= 0 or not os.path.isdir(backup_dir):
        return []

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=keep_days)
    removed: list[str] = []
    for name in sorted(os.listdir(backup_dir)):
        if not _is_dump(name):
            continue
        path = os.path.join(backup_dir, name)
        try:
            modified = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        except OSError:
            continue
        if modified < cutoff:
            _discard(path)
            removed.append(path)
            logger.info("按保留 %d 天清掉旧备份 %s", keep_days, path)
    return removed


def latest_backup(backup_dir: str) -> str | None:
    """Newest dump in ``backup_dir`` (by mtime), or None when there isn't one.

    The daily job says nothing on success, so this is how "is the database still
    insured?" gets answered without digging through the folder by hand.
    """
    if not os.path.isdir(backup_dir):
        return None
    dumps = [
        os.path.join(backup_dir, name)
        for name in os.listdir(backup_dir)
        if _is_dump(name)
    ]
    if not dumps:
        return None
    return max(dumps, key=lambda p: os.path.getmtime(p))


def _discard(path: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(path)
