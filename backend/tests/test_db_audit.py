"""迁移前审计的用例。

真正跑一遍 `data/videos.db` 只会得到「一切正常」，那正好是检查悄悄失效时的样子，所以
这里造一个故意脏的库：每种 PG 会拒收的数据都塞一条进去，逐个确认对应类别真的报了。
建表全走裸 SQL——用 ``create_all`` 出来的库和模型完全一致，脏数据根本造不出来。
"""

import sqlite3
from datetime import datetime, timezone

import pytest

from src.database.base import Base
from src.db_audit import CATEGORIES, audit, canonical_value, open_read_only, render_report
from src.models.video import Video


@pytest.fixture
def messy_db(tmp_path):
    """一个每类问题都有一条的库，路径给审计脚本以只读方式打开。

    表名和列名都按真模型写，故意的偏差只有三处：``users.username`` 在库里可空而模型
    说 NOT NULL（这样才塞得进 NULL），``users`` 多两列模型没有的遗留列，``leftover``
    是模型完全不认识的表。其余脏在值里。
    """
    path = tmp_path / "messy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE video_sources (
            id INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            path VARCHAR(1024) NOT NULL,
            type VARCHAR(50) NOT NULL,
            scan_interval INTEGER NOT NULL DEFAULT 3600,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(64),
            password_hash VARCHAR(128) NOT NULL,
            role VARCHAR(20) NOT NULL,
            display_name VARCHAR(64),
            is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            last_login_at DATETIME,
            legacy_filled INTEGER,
            legacy_empty INTEGER
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            filepath VARCHAR(1024) NOT NULL,
            title VARCHAR(512),
            duration INTEGER,
            file_size BIGINT,
            is_missing BOOLEAN NOT NULL DEFAULT 0,
            rating INTEGER NOT NULL DEFAULT 0,
            view_count INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE favorites (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY,
            type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            message VARCHAR,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data JSON NOT NULL
        );
        CREATE TABLE leftover (id INTEGER);
        """
    )
    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    # 父表先备好两行，孤儿行才是「指向了不存在的那一个」而不是整表误报
    conn.executemany(
        "INSERT INTO video_sources (id, name, path, type) VALUES (?, ?, ?, 'local')",
        [(1, "本机", "/media"), (2, "NAS", "/nas")],
    )
    # 干净的一行：不希望对它报任何数据类问题
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, created_at,"
        " legacy_filled, legacy_empty) VALUES (1, 'owner', 'hash', 'owner', 1, ?, 0, NULL)",
        (now,),
    )
    conn.execute(
        "INSERT INTO videos (id, source_id, filepath, title, duration, file_size,"
        " is_missing, created_at) VALUES (1, 1, '/m/a.mp4', '干净', 100, 2048, 0, ?)",
        (now,),
    )
    conn.execute("INSERT INTO favorites (id, user_id, video_id) VALUES (1, 1, 1)")
    # NULL 进 NOT NULL 列：库里这列可空，所以存得下
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, created_at)"
        " VALUES (2, NULL, 'hash', 'member', 1, ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, created_at,"
        " legacy_filled) VALUES (3, 'someone', 'hash', 'member', 1, ?, 1)",
        (now,),
    )
    # 一条视频把所有值类问题占满：超长、类型错、坏日期
    conn.execute(
        "INSERT INTO videos (id, source_id, filepath, title, duration, file_size,"
        " is_missing, created_at) VALUES (2, 1, '/m/bad.mp4', ?, 'abc', ?, 7, 'not-a-date')",
        ("超长" * 300, 4096),
    )
    # 一条视频把范围问题和孤儿行占满：source_id 指向不存在的源，整数超出 PG 的 integer
    conn.execute(
        "INSERT INTO videos (id, source_id, filepath, title, duration, created_at)"
        " VALUES (3, 999, '/m/orphan.mp4', '没人', 4000000000000, ?)",
        (now,),
    )
    # 收藏两边都指空：归属列在库里从来没有外键约束
    conn.execute("INSERT INTO favorites (id, user_id, video_id) VALUES (2, 404, 404)")
    # JSON 列里存了不是 JSON 的文本；BLOB 存进 VARCHAR 列是 SQLite 亲和唯一放过的那类
    conn.execute(
        "INSERT INTO notifications (id, type, title, data) VALUES (1, 'scan', 't', 'not json')"
    )
    conn.execute(
        "INSERT INTO notifications (id, type, title, data)"
        " VALUES (2, 'scan', '要被改成 BLOB', '{\"a\":1}')"
    )
    conn.execute("UPDATE notifications SET title = x'00ff10' WHERE id = 2")
    conn.commit()
    conn.close()
    return path


def categories(result) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for finding in result.findings:
        out.setdefault(finding.category, []).append(finding.detail)
    return out


def details(result, category: str) -> str:
    return "\n".join(categories(result).get(category, []))


@pytest.fixture
def findings(messy_db):
    return audit(messy_db)


def test_detects_orphan_rows(findings):
    """模型声明的外键指空了要报出来，PG 建表后会直接拒绝这些行。"""
    text = details(findings, "orphan_row")
    assert "videos.source_id=999" in text
    assert "favorites.user_id=404" in text
    assert "favorites.video_id=404" in text
    assert all(f.blocking for f in findings.findings if f.category == "orphan_row")


def test_valid_foreign_keys_are_not_reported(findings):
    """指向存在的父行不能报，否则每张有外键的表都会被整表误报成孤儿。"""
    text = details(findings, "orphan_row")
    assert "favorites.user_id=1" not in text
    assert "favorites.video_id=1" not in text
    assert "videos.source_id=1" not in text


def test_detects_over_length(findings):
    assert "videos.title 长度" in details(findings, "over_length")
    assert "上限 512" in details(findings, "over_length")


def test_detects_type_mismatch(findings):
    text = details(findings, "type_mismatch")
    assert "videos.duration 存的是文本 'abc'" in text
    assert "videos.is_missing 布尔列里存了 7" in text
    assert "notifications.title 存的是 BLOB" in text


def test_detects_int_overflow(findings):
    text = details(findings, "int_overflow")
    assert "videos.duration 值 4000000000000 超出 PG 的 integer 范围" in text
    # BIGINT 在 PG 那边是 64 位，同样的数值不该报
    assert "file_size" not in text


def test_detects_not_null_violation(findings):
    assert "users.username 有 NULL" in details(findings, "not_null_violation")


def test_detects_bad_datetime(findings):
    assert "videos.created_at 的时间解析不了" in details(findings, "bad_datetime")


def test_detects_bad_json(findings):
    assert "notifications.data 不是合法 JSON" in details(findings, "bad_json")


def test_reports_db_only_column_holding_data(findings):
    """遗留列真存了值才算丢数据，全空的那列只是噪音。"""
    text = details(findings, "schema_drift")
    assert "users.legacy_filled" in text
    assert "有 1 行存了值" in text
    assert "users.legacy_empty 只存在于库里（模型没有），全是空值/0" in text
    blocking = [f.detail for f in findings.findings if f.blocking]
    assert any("legacy_filled" in d for d in blocking)
    assert not any("legacy_empty" in d for d in blocking)


def test_reports_table_missing_from_models(findings):
    assert "库里的表 leftover 模型里没有" in details(findings, "schema_drift")


def test_notes_unenforced_foreign_keys(findings):
    """SQLite 里 ALTER 加的归属列没有约束，这条要提示但不阻断。"""
    text = details(findings, "missing_fk_constraint")
    assert "favorites.user_id" in text
    assert all(not f.blocking for f in findings.findings if f.category == "missing_fk_constraint")


def test_reports_every_declared_check(findings):
    """报告按类别分节时不能漏掉任何一类检查。"""
    rendered = render_report(findings)
    for _key, title in CATEGORIES:
        assert title in rendered


def test_digest_is_stable_across_row_order(messy_db, tmp_path):
    """同样的数据换个插入顺序要得到同一个摘要，否则 P3 没法拉着两边比。"""
    first = {t.name: t.digest for t in audit(messy_db).tables}

    swapped = tmp_path / "swapped.db"
    conn = sqlite3.connect(swapped)
    src = sqlite3.connect(messy_db)
    for (name,) in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        ddl = src.execute(f"SELECT sql FROM sqlite_master WHERE name='{name}'").fetchone()[0]
        conn.execute(ddl)
        rows = list(src.execute(f'SELECT * FROM "{name}" ORDER BY rowid DESC'))
        if rows:
            conn.executemany(
                f'INSERT INTO "{name}" VALUES ({",".join("?" * len(rows[0]))})', rows
            )
    conn.commit()
    conn.close()

    second = {t.name: t.digest for t in audit(swapped).tables}
    assert first["users"] == second["users"]
    assert first["videos"] == second["videos"]


def test_bool_and_text_timestamps_canonicalise_alike():
    """SQLite 的 0/1 和文本时间要归一成 PG 那种形式，两边才可能算出相同摘要。"""
    col = Video.__table__.columns["is_missing"]
    assert canonical_value(col, 0) == "false"
    assert canonical_value(col, True) == "true"

    when = Video.__table__.columns["created_at"]
    assert canonical_value(when, "2026-01-02 03:04:05") == "2026-01-02T03:04:05+00:00"
    assert canonical_value(when, None) == "\u2205"


def test_audit_never_writes(messy_db):
    """审计必须只读：库文件一个字节都不能变。"""
    before = messy_db.read_bytes()
    audit(messy_db)
    audit(messy_db)
    assert messy_db.read_bytes() == before


def test_opened_connection_refuses_writes(messy_db):
    conn = open_read_only(messy_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE videos SET title = 'hacked' WHERE id = 1")
    finally:
        conn.close()


def test_clean_database_has_no_blocking_findings(tmp_path):
    """按模型原样写入的库必须干干净净，否则是检查自己在瞎报。

    行全部走 ORM 而不是裸 SQL：Python 侧默认值（时间戳、is_missing 那批）只有模型自己
    知道，手写 INSERT 漏一个 NOT NULL 列就先被 SQLite 拒了，报不到审计上。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.models.favorite import Favorite
    from src.models.notification import Notification
    from src.models.source import VideoSource
    from src.models.user import ROLE_OWNER, User
    from src.models.video import Video

    path = tmp_path / "clean.db"
    engine = create_engine(f"sqlite:///{path}")
    # 只建这几张表：模型里其余的表在这个库里不存在，报出来的是不阻断的「待补表」
    for name in ("video_sources", "users", "videos", "favorites", "notifications"):
        Base.metadata.tables[name].create(engine)

    with Session(engine) as session:
        source = VideoSource(name="本机", path="/media", type="local")
        user = User(username="owner", password_hash="hash", role=ROLE_OWNER)
        session.add_all([source, user])
        session.flush()
        video = Video(source_id=source.id, filepath="/m/a.mp4", title="正常", duration=100)
        session.add(video)
        session.flush()
        session.add(Favorite(user_id=user.id, video_id=video.id))
        session.add(Notification(type="scan", title="扫描完成", data={"count": 1}))
        session.commit()

    result = audit(path)
    assert [f.detail for f in result.blocking] == []
    assert {t.name: t.rows for t in result.tables} == {
        "video_sources": 1,
        "users": 1,
        "videos": 1,
        "favorites": 1,
        "notifications": 1,
    }
