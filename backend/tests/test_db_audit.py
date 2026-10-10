"""迁移前审计的用例。

真正跑一遍 `data/videos.db` 只会得到「一切正常」，那正好是检查悄悄失效时的样子，所以
这里造一个故意脏的库：每种 PG 会拒收的数据都塞一条进去，逐个确认对应类别真的报了。
建表全走裸 SQL——用 ``create_all`` 出来的库和模型完全一致，脏数据根本造不出来。

后半截钉的是这批检查的**边界**：同一类问题报满五条之后怎么收口、库里根本没有这一列/
这张父表时为什么不报、父表只是库里遗留的一张陌生表时为什么不查、复合外键为什么不 walk，
以及那个命令行出口（报告落在哪、控制台为什么必须是 ASCII）。这几格在真库里永远不会
同时出现，所以只有造得出现场的库才敲得到。
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, ForeignKeyConstraint, Integer, MetaData, Table

from src.database.base import Base
from src.db_audit import (
    CATEGORIES,
    SAMPLES_PER_CHECK,
    AuditResult,
    _audit_table,
    _is_type_violation,
    audit,
    canonical_value,
    main,
    open_read_only,
    render_report,
)
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
    # 解析不了的那一格不能抛：整表摘要要把每一行都算进去才算搬全，撞成同一个串就是漏搬
    assert canonical_value(when, "not-a-date").startswith("<坏时间:")
    assert canonical_value(when, "not-a-date") != canonical_value(when, "2026-13-45")


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


# ------------------------------------------------------- 这批检查的边界与 CLI 出口

#: 下面这些库只写用得到的列，且列类型全用裸 SQL 声明：库里那一列的声明决定 SQLite 给它的
#: 亲和，而亲和决定一格值最终以什么形状存着——审计看的正是存着的形状，不是模型的声明。
#: 时间列一律可空且插入时省略，免得断言里混进一条「NOT NULL 列里有 NULL」。
SRC_DDL = (
    "CREATE TABLE video_sources (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL,"
    " path VARCHAR(1024) NOT NULL, type VARCHAR(50) NOT NULL)"
)
VIDEO_DDL = (
    "CREATE TABLE videos (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL,"
    " filepath VARCHAR(1024) NOT NULL, title VARCHAR(512), duration INTEGER,"
    " created_at DATETIME)"
)
USER_DDL = (
    "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL,"
    " is_active BOOLEAN NOT NULL)"
)
FAVORITE_DDL = (
    "CREATE TABLE favorites (id INTEGER PRIMARY KEY, user_id INTEGER,"
    " video_id INTEGER NOT NULL)"
)
NOTIF_DDL = (
    "CREATE TABLE notifications (id INTEGER PRIMARY KEY, type VARCHAR(50) NOT NULL,"
    " title VARCHAR(255) NOT NULL, data JSON NOT NULL)"
)
GOOD_STAMP = "2026-01-02 03:04:05"


def build_db(tmp_path: Path, name: str, ddl: list[str], rows: list[str]) -> Path:
    """按裸 SQL 建一个小库，路径交给 audit，它自己会以只读方式打开。"""
    path = tmp_path / name
    conn = sqlite3.connect(path)
    for statement in ddl + rows:
        conn.execute(statement)
    conn.commit()
    conn.close()
    return path


def items(result, category: str) -> list[tuple[bool, str]]:
    """带阻断标记一起取：只断言正文的话，看不出这条到底挡不挡迁移。"""
    return [(f.blocking, f.detail) for f in result.findings if f.category == category]


def test_timestamp_column_holding_a_number_trips_both_gates(tmp_path):
    """库里那列声明成 DATETIME，SQLite 给它的亲和是 NUMERIC，所以整数真的以整数存着。

    同一格踩中两道检查：值不是文本（type_mismatch），也不是能解析的文本（bad_datetime），
    两条都阻断——PG 不替这种值做转换，导入会当场拒收。整数走「秒」那条出口、浮点走
    「不是文本」那条出口，报告里说的是两种不同的现场，所以两句都得钉住。
    """
    db = build_db(
        tmp_path,
        "epoch.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO videos (id, source_id, filepath, created_at) VALUES (1, 1, '/m/1.mp4',"
            f" '{GOOD_STAMP}')",
            "INSERT INTO videos (id, source_id, filepath, created_at) VALUES (2, 1, '/m/2.mp4',"
            " 1700000000)",
            "INSERT INTO videos (id, source_id, filepath, created_at) VALUES (3, 1, '/m/3.mp4',"
            " 1700000000.5)",
        ],
    )
    result = audit(db)
    assert items(result, "type_mismatch") == [
        (True, "videos.created_at 存的是 整数"),
        (True, "videos.created_at 存的是 浮点数"),
    ]
    assert items(result, "bad_datetime") == [
        (True, "videos.created_at 的时间解析不了：1700000000"),
        (True, "videos.created_at 的时间解析不了：1700000000.5"),
    ]
    # 文本时间那一行不报：否则这一族每一行都会被拉进阻断项，检查就成了瞎报
    assert len(result.blocking) == 4


def test_affinity_hides_a_number_stored_in_a_text_column(tmp_path):
    """往 VARCHAR 列里塞整数，SQLite 当场把它转成文本，审计一条也报不出来。

    这条是负对照，钉的是「为什么上面那格要借 DATETIME/JSON 列」：后来人简化用例时最可能
    做的就是改成往 title 里塞数字，改完用例照绿，敲的却不再是同一条分支。
    """
    db = build_db(
        tmp_path,
        "affinity.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO videos (id, source_id, filepath, title) VALUES (1, 1, '/m/1.mp4', 12345)",
        ],
    )
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT typeof(title) FROM videos").fetchone()[0] == "text"
    finally:
        conn.close()
    result = audit(db)
    assert items(result, "type_mismatch") == []
    assert items(result, "over_length") == []


def test_a_number_in_a_json_column_is_two_blocking_findings(tmp_path):
    """JSON 列存裸数字：类型一道闸门、JSON 一道闸门，两条都阻断，且是同格的两个症状。

    「不是合法 JSON」这句字面上不精确（12345 本身是个合法 JSON 标量），结论却是对的：
    摘要那侧 ``canonical_value`` 会把这一格收成 ``<坏JSON:12345>`` 这样的字面串，真搬进 PG
    就是一次静默改值。审计先挡住，才轮到那句不精确的措辞。
    """
    db = build_db(
        tmp_path,
        "json.db",
        [NOTIF_DDL],
        [
            "INSERT INTO notifications (id, type, title, data) VALUES (1, 'scan', 't', 12345)",
            "INSERT INTO notifications (id, type, title, data) VALUES (2, 'scan', 't', 1.5)",
        ],
    )
    result = audit(db)
    assert items(result, "type_mismatch") == [
        (True, "notifications.data 存的是 整数"),
        (True, "notifications.data 存的是 浮点数"),
    ]
    assert items(result, "bad_json") == [
        (True, "notifications.data 不是合法 JSON：12345"),
        (True, "notifications.data 不是合法 JSON：1.5"),
    ]
    col = Base.metadata.tables["notifications"].columns["data"]
    assert canonical_value(col, 12345) == "<坏JSON:12345>"


def test_a_blob_in_an_integer_column_is_a_shape_problem_not_a_range_one(tmp_path):
    """BLOB 是唯一一种 SQLite 不会转换、于是真能以原形状存进来的值。

    同格里 1700000000 存进 duration（INTEGER 列）什么事都没有——报的是这一列的形状，
    不是这个数值。上限检查也因此不能被这一格触发：bytes 不是 int。
    """
    db = build_db(
        tmp_path,
        "blob.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO videos (id, source_id, filepath, duration) VALUES (1, 1, '/m/1.mp4',"
            " x'00ff10')",
            "INSERT INTO videos (id, source_id, filepath, duration) VALUES (2, 1, '/m/2.mp4',"
            " 1700000000)",
        ],
    )
    result = audit(db)
    assert items(result, "type_mismatch") == [(True, "videos.duration 存的是 BLOB")]
    assert items(result, "int_overflow") == []


def test_values_sitting_exactly_on_a_limit_are_not_reported(tmp_path):
    """长度刚好等于上限、整数刚好是 PG integer 的最大值：这两个都不算问题。

    把「超过」写成「达到」的那一步，只有正好卡在边界上的行才抓得住，而真库里没有这种行，
    所以只能现造。同一个库里再放一行各超一点的，证明这两条闸门本身是活的、不是被顺手关掉。

    第三行走的是另一件事：BIGINT 在 PG 那边还是 64 位，所以 2 的 40 次方这种远超 int32
    的数值不该报——它和 duration 那条撞在同一个整数上限上的区别，只有把两种列都放进
    同一个库才看得出来。
    """
    at_len = "x" * 512
    over_len = "x" * 513
    videos_ddl = (
        "CREATE TABLE videos (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL,"
        " filepath VARCHAR(1024) NOT NULL, title VARCHAR(512), duration INTEGER,"
        " file_size BIGINT, created_at DATETIME)"
    )
    db = build_db(
        tmp_path,
        "limits.db",
        [SRC_DDL, videos_ddl],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO videos (id, source_id, filepath, title, duration)"
            f" VALUES (1, 1, '/m/1.mp4', '{at_len}', 2147483647)",
            "INSERT INTO videos (id, source_id, filepath, title, duration)"
            f" VALUES (2, 1, '/m/2.mp4', '{over_len}', 2147483648)",
            "INSERT INTO videos (id, source_id, filepath, file_size)"
            " VALUES (3, 1, '/m/3.mp4', 1099511627776)",
        ],
    )
    result = audit(db)
    assert items(result, "over_length") == [(True, "videos.title 长度 513，模型上限 512")]
    assert items(result, "int_overflow") == [
        (True, "videos.duration 值 2147483648 超出 PG 的 integer 范围")
    ]


def test_the_sample_cap_lists_five_then_one_note_per_table(tmp_path):
    """上限是按「类别 × 表」记的：一张表报满了，不会把另一张表一起压掉。

    第七行孤儿换到的是五行样本加一句「还有更多」，那一句也带着阻断标记——所以报告头
    上的「阻断项」数是六而不是七。这里钉的是测量结果：元行算一条是有意的（它替没列出来的
    那些行挡着迁移），但它让计数不等于行数，值得写在纸面上。
    """
    videos = [
        f"INSERT INTO videos (id, source_id, filepath) VALUES ({i}, {500 + i}, '/m/{i}.mp4')"
        for i in range(1, 8)
    ]
    favorites = [
        "INSERT INTO favorites (id, user_id, video_id) VALUES (1, 404, 1)",
        "INSERT INTO favorites (id, user_id, video_id) VALUES (2, 404, 1)",
        "INSERT INTO favorites (id, user_id, video_id) VALUES (3, 404, 2)",
    ]
    db = build_db(
        tmp_path,
        "cap.db",
        [SRC_DDL, VIDEO_DDL, USER_DDL, FAVORITE_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (6, 's6', '/m6', 'local')",
            "INSERT INTO users (id, username, is_active) VALUES (1, 'owner', 1)",
            "INSERT INTO videos (id, source_id, filepath) VALUES (8, 6, '/m/8.mp4')",
            *videos,
            *favorites,
        ],
    )
    result = audit(db)
    orphans = items(result, "orphan_row")
    # 表名按字母序扫，favorites 先到，videos 后到；三行 favorites 全都报了
    assert [d for _b, d in orphans[:3]] == [
        "favorites.user_id=404 在 users 里找不到父行" for _ in range(3)
    ]
    assert all(b for b, _d in orphans)
    assert orphans[-1] == (
        True,
        f"videos：同类问题还有更多，本表只列前 {SAMPLES_PER_CHECK} 条",
    )
    listed = [d for _b, d in orphans if d.startswith("videos.source_id")]
    assert len(listed) == SAMPLES_PER_CHECK  # 第五行之后的那一行换成上面那句元行
    assert "videos.source_id=506" not in "\n".join(d for _b, d in orphans)
    assert "videos.source_id=507" not in "\n".join(d for _b, d in orphans)
    # 那句「还有更多」整张表只出现一次，所以总数是三加五再加一，而不是七加三
    assert len(orphans) == 3 + SAMPLES_PER_CHECK + 1
    assert len(result.blocking) == len(orphans)


def test_the_extra_note_line_appears_only_after_the_cap(tmp_path):
    """正好五条不该有第六条；第六条才换来那句「还有更多」，第七条起一句不多。"""
    def build(name: str, count: int):
        rows = [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
        ]
        rows += [
            f"INSERT INTO videos (id, source_id, filepath) VALUES ({i}, 999, '/m/{i}.mp4')"
            for i in range(1, count + 1)
        ]
        return audit(build_db(tmp_path, name, [SRC_DDL, VIDEO_DDL], rows))

    at_cap = build("cap5.db", SAMPLES_PER_CHECK)
    over_cap = build("cap6.db", SAMPLES_PER_CHECK + 1)
    assert items(at_cap, "orphan_row") == [
        (True, "videos.source_id=999 在 video_sources 里找不到父行")
        for _ in range(SAMPLES_PER_CHECK)
    ]
    assert len(over_cap.findings) - len(at_cap.findings) == 1
    assert items(over_cap, "orphan_row")[-1] == (
        True,
        f"videos：同类问题还有更多，本表只列前 {SAMPLES_PER_CHECK} 条",
    )


def test_foreign_key_columns_that_the_audit_deliberately_skips(tmp_path):
    """模型里现在没有复合外键；哪天有了，这一族不能把整张表误报成孤儿。

    两张子表在库里形状完全一样（同一对列、同样指向不存在的 999），差别只在约束是两列还是
    一列：一列的那张报了孤儿，两列的一张不报。这才说明被跳过的原因是「复合」，而不是
    「这一列压根没被查」。直接喂 ``_audit_table`` 是因为这是唯一能造出复合约束的入口。

    第三张子表走的是另一条跳过理由：约束是单列的、父表在库里实实在在存在，可模型不认识
    那个名字——这种表整个会在迁移时被丢掉，该管它的是 schema_drift 而不是孤儿行。
    """
    meta = MetaData()
    # db_audit 只问父表**名字**在不在模型里，所以这层 MetaData 自洽就能把约束解出来。
    Table("videos", meta, Column("id", Integer, primary_key=True), Column("source_id", Integer))
    composite = Table(
        "composite_child",
        meta,
        Column("a", Integer),
        Column("b", Integer),
        ForeignKeyConstraint(["a", "b"], ["videos.id", "videos.source_id"]),
    )
    single = Table(
        "single_child",
        meta,
        Column("a", Integer),
        Column("b", Integer),
        ForeignKeyConstraint(["a"], ["videos.id"]),
    )
    # 第三种跳过理由：父表在这个库里真有，模型却不认识它。这种表整张会在迁移时被丢掉，
    # 孤儿行不是这里该说的（该说的是 schema_drift），所以这一列也不查。
    Table("legacy_parent", meta, Column("id", Integer, primary_key=True))
    named = Table(
        "named_child",
        meta,
        Column("a", Integer),
        Column("b", Integer),
        ForeignKeyConstraint(["a"], ["legacy_parent.id"]),
    )
    assert {len(fk.constraint.columns) for fk in composite.foreign_keys} == {2}
    assert {len(fk.constraint.columns) for fk in single.foreign_keys} == {1}
    assert {len(fk.constraint.columns) for fk in named.foreign_keys} == {1}
    assert "legacy_parent" not in Base.metadata.tables

    db = build_db(
        tmp_path,
        "fk.db",
        [
            "CREATE TABLE videos (id INTEGER PRIMARY KEY, source_id INTEGER)",
            "CREATE TABLE legacy_parent (id INTEGER PRIMARY KEY)",
            "CREATE TABLE composite_child (a INTEGER, b INTEGER)",
            "CREATE TABLE single_child (a INTEGER, b INTEGER)",
            "CREATE TABLE named_child (a INTEGER, b INTEGER)",
        ],
        [
            "INSERT INTO videos (id, source_id) VALUES (1, 1)",
            "INSERT INTO legacy_parent (id) VALUES (1)",
            "INSERT INTO composite_child (a, b) VALUES (999, 999)",
            "INSERT INTO single_child (a, b) VALUES (999, 999)",
            # 三张子表的值一样：指向的都是不存在的 999，只有该查的那一张报了
            "INSERT INTO named_child (a, b) VALUES (999, 999)",
        ],
    )
    conn = open_read_only(db)
    found: dict[str, list[tuple[str, str]]] = {}
    try:
        for name, table in (
            ("composite_child", composite),
            ("single_child", single),
            ("named_child", named),
        ):
            result = AuditResult(db_path=str(db))
            _audit_table(conn, name, table, {"a", "b"}, {}, result)
            found[name] = [(f.category, f.detail) for f in result.findings]
            # 跳过外键不等于跳过这张表：行还是要数、摘要还是要算
            assert [(t.name, t.rows) for t in result.tables] == [(name, 1)]
            assert result.tables[0].digest != ""
    finally:
        conn.close()
    assert found["composite_child"] == []
    assert found["named_child"] == []
    assert found["single_child"] == [
        ("orphan_row", "single_child.a=999 在 videos 里找不到父行")
    ]


def test_an_old_library_without_the_ownership_column_judges_only_what_is_there(tmp_path):
    """M2 之前的 favorites 根本没有 user_id：这一列不能被判成孤儿。

    库里没这一列，子列就查不了（跳过），而 video_id 那列照判。schema_drift 会另报一句
    「模型里有而库里没有：迁移时补列」，所以这不是漏报，是同一件事由更合适的类别说一遍。
    """
    db = build_db(
        tmp_path,
        "old.db",
        [
            SRC_DDL,
            VIDEO_DDL,
            USER_DDL,
            "CREATE TABLE favorites (id INTEGER PRIMARY KEY, video_id INTEGER NOT NULL)",
        ],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO users (id, username, is_active) VALUES (1, 'owner', 1)",
            "INSERT INTO videos (id, source_id, filepath) VALUES (1, 1, '/m/1.mp4')",
            "INSERT INTO favorites (id, video_id) VALUES (1, 1)",
            "INSERT INTO favorites (id, video_id) VALUES (2, 999)",
        ],
    )
    result = audit(db)
    assert items(result, "orphan_row") == [
        (True, "favorites.video_id=999 在 videos 里找不到父行")
    ]
    assert "user_id" not in details(result, "orphan_row")
    assert "favorites.user_id 模型里有而库里没有：迁移时补列（正常）" in details(
        result, "schema_drift"
    )


def test_a_missing_parent_table_is_not_reported_as_a_table_full_of_orphans(tmp_path):
    """父表整个读不出来时这一列不判——而不是判成整表孤儿（同 #184 那次改口的方向）。

    一个现场里两条列正好对照：user_id 的父表 users 读得出来，404 被如实报成孤儿；
    video_id 的父表 videos 在这个库里根本不存在，那一行的 7 就一条不报。缺的表由
    schema_drift 另报一句，所以「判不了」不是「悄悄不说」。
    """
    db = build_db(
        tmp_path,
        "noparent.db",
        [SRC_DDL, USER_DDL, FAVORITE_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO users (id, username, is_active) VALUES (1, 'owner', 1)",
            "INSERT INTO favorites (id, user_id, video_id) VALUES (1, 404, 404)",
            "INSERT INTO favorites (id, user_id, video_id) VALUES (2, 1, 7)",
        ],
    )
    result = audit(db)
    assert items(result, "orphan_row") == [
        (True, "favorites.user_id=404 在 users 里找不到父行")
    ]
    assert "模型里的表 videos 库里没有：迁移时新建（正常）" in details(result, "schema_drift")
    assert [t.name for t in result.tables] == ["favorites", "users", "video_sources"]


def test_a_null_foreign_key_value_is_not_an_orphan(tmp_path):
    """归属列存了 NULL：报的是 NOT NULL 那一条，不是「找不到父行」。

    库里那列可空（模型说 NOT NULL），所以 NULL 存得进来。这一格在孤儿循环里必须直接跳过：
    NULL 不是任何父表的键，不跳的话它会被报成一条指向不存在的父行的孤儿，把同一件事报两遍，
    而且第二遍还是错的说法。
    """
    db = build_db(
        tmp_path,
        "nullfk.db",
        [SRC_DDL, VIDEO_DDL, USER_DDL, FAVORITE_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO users (id, username, is_active) VALUES (1, 'owner', 1)",
            "INSERT INTO videos (id, source_id, filepath) VALUES (1, 1, '/m/1.mp4')",
            "INSERT INTO favorites (id, user_id, video_id) VALUES (1, NULL, 1)",
        ],
    )
    result = audit(db)
    assert items(result, "orphan_row") == []
    assert items(result, "not_null_violation") == [
        (True, "favorites.user_id 有 NULL，但模型声明 NOT NULL")
    ]


def test_a_null_in_a_modelled_default_column_stays_quiet(tmp_path):
    """模型说 NOT NULL 但带默认值、库里那一列是漂移出来的可空列且有 NULL：审计不报。

    同一件事由两处说，各管一半：审计只管「这一格现在的形状迁过去会不会出问题」，而「这行
    到底进不进得了 PG」由 ``db_transfer._null_in_required`` 逐表算——它对带默认值的列一样
    会报。这里钉的是审计这一侧保持安静，免得哪天有人把它改成同一件事双重报警。
    """
    db = build_db(
        tmp_path,
        "default_col.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            # created_at 在库里可空（VIDEO_DDL 就这么声明的），这一行又省略了它
            "INSERT INTO videos (id, source_id, filepath) VALUES (1, 1, '/m/1.mp4')",
        ],
    )
    result = audit(db)
    assert items(result, "not_null_violation") == []
    assert [f.detail for f in result.blocking] == []


def test_the_report_marks_categories_that_found_nothing(tmp_path):
    """一个还没扫过的空库：九类检查里有八类是空的，每一类都要打出一个「无。」。

    这是唯一能让所有数据类检查同时为空的现场——上面那些库九类全命中，所以「无。」那一格
    到今天一次也没被走到过。断言数的是标记的个数而不是正文，因为类别标题里也带着字。
    """
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    result = audit(empty)
    rendered = render_report(result)
    assert {f.category for f in result.findings} == {"schema_drift"}
    assert rendered.count("无。") == len(CATEGORIES) - 1
    assert "扫描的表：0 张，合计 0 行" in rendered
    assert "**阻断项：0 条**" in rendered


def test_the_type_gate_treats_a_missing_value_as_legal():
    """``_is_type_violation`` 的 NULL 出口走不到：审计在上一层就把 None 拦下了。

    它不是死码——这是那道「只有直接敲才走得通」的保险（同 #199 的两道依赖）。这里用等式
    而不是 pragma：pragma 会说「没有测试能到这里」，而这一句 ``_is_type_violation(col, None)
    is None`` 就到得了。三种列各敲一次，免得哪天只有 String 那一支还认 NULL。
    """
    columns = Base.metadata.tables["videos"].columns
    assert _is_type_violation(columns["title"], None) is None
    assert _is_type_violation(columns["duration"], None) is None
    assert _is_type_violation(columns["is_missing"], None) is None


def test_the_cli_refuses_a_missing_database(tmp_path, capsys):
    """库不在就别写报告：退出码 2，报告文件一个字节也不留。"""
    out = tmp_path / "report.md"
    assert main(["--db", str(tmp_path / "nope.db"), "--out", str(out)]) == 2
    assert not out.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("db not found:")
    assert "nope.db" in captured.err


def test_the_cli_writes_a_utf8_report_and_an_ascii_summary(tmp_path, capsys):
    """报告文件里是中文，stdout 必须是纯 ASCII——控制台是 cp936，中文会花掉。

    顺手钉住 stdout 那几行的顺序：类别计数按 CATEGORIES 的顺序打，且只打非零的那些；
    这条顺序是给人比对两次报告用的，换个顺序就比不出来了。
    """
    db = build_db(
        tmp_path,
        "site.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
            "INSERT INTO videos (id, source_id, filepath, duration) VALUES (1, 999, '/m/1.mp4',"
            " x'00ff10')",
        ],
    )
    out = tmp_path / "report.md"
    assert main(["--db", str(db), "--out", str(out)]) == 0
    captured = capsys.readouterr()
    assert all(ord(ch) < 128 for ch in captured.out)
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines[0] == "tables=2 rows=2"
    assert lines[-1] == f"report={out}"
    assert lines[-2] == "blocking=2"
    assert "orphan_row=1" in lines
    assert "type_mismatch=1" in lines
    assert lines.index("orphan_row=1") < lines.index("type_mismatch=1")
    assert "over_length=0" not in captured.out
    report = out.read_text(encoding="utf-8")
    assert "## 按类别" in report
    assert "找不到父行" in report
    assert "存的是 BLOB" in report


def test_the_cli_names_the_report_after_the_database_by_default(tmp_path, capsys):
    """不给 --out 时报告落在库旁边、按日期命名——迁库的人不必记着传第二个参数。

    日期只在文件名里，不进断言：跨零点跑测试时它自己会变，这里要钉的是落在哪个目录、
    是不是一个真的报告，不是它叫哪天。
    """
    db = build_db(
        tmp_path,
        "site.db",
        [SRC_DDL, VIDEO_DDL],
        [
            "INSERT INTO video_sources (id, name, path, type)"
            " VALUES (1, '本机', '/m', 'local')",
        ],
    )
    assert main(["--db", str(db)]) == 0
    # 扫了两张表、只有一行数据：报表里那两个数各说各的，混在一起就核不出夹具坏了没有
    assert capsys.readouterr().out.splitlines()[0] == "tables=2 rows=1"
    produced = sorted(tmp_path.glob("migration-audit-*.md"))
    assert [p.parent for p in produced] == [tmp_path]
    assert len(produced) == 1
    assert produced[0].read_text(encoding="utf-8").startswith("# PG 迁移前审计")

