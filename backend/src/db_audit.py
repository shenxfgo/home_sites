"""把 SQLite 库迁到 PostgreSQL 之前的只读审计。

用途很窄但必须是第一步：PostgreSQL 会拒绝一批 SQLite 一直默默收下的数据。四类风险
都能在代码里预先发现而不是等业务报错：库里实际存的值不符合模型声明的列（类型、长度、
NOT NULL、32 位整数范围）、按模型外键查出的孤儿行（SQLite 默认不强制外键，所以这些行
真的可能存在）、库与模型的 schema 漂移（只存在于库里的列在迁移后会丢数据）、以及日期
与 JSON 列里解析不了的文本。

这个模块只以 ``mode=ro`` 打开数据库文件，不写任何东西；也不 import ``src.database.``
的任何东西，免得顺带把 engine 建出来——审计只需要模型的元数据和标准库 sqlite3。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Table
from sqlalchemy.types import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
)

import src.models  # noqa: F401  # 只为把全部模型注册进 Base.metadata，包本身是空的导出面
from src.config import BACKEND_ROOT
from src.database.base import Base

DEFAULT_DB = BACKEND_ROOT / "data" / "videos.db"

# 每种检查在报告里最多列几条样本，再多就把报告冲没了。
SAMPLES_PER_CHECK = 5

# PG 的 INTEGER 是 32 位，SQLite 的 INTEGER 是 64 位：过去写得进去、迁过去会直接报错。
INT32_RANGE = (-(2**31), 2**31 - 1)
INT64_RANGE = (-(2**63), 2**63 - 1)

NULL = "\u2205"  # 报告里区分「空串」和「NULL」


@dataclass
class Finding:
    category: str
    detail: str
    blocking: bool


@dataclass
class TableAudit:
    name: str
    rows: int = 0
    digest: str = ""


@dataclass
class AuditResult:
    db_path: str
    findings: list[Finding] = field(default_factory=list)
    tables: list[TableAudit] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]


def open_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _db_tables(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    return {n: list(conn.execute(f'PRAGMA table_info("{n}")')) for n in names}


def _is_type_violation(col: Column, value: Any) -> str | None:
    """值本身放不进这一列时返回一句原因，合法时返回 None。"""
    if value is None:
        return None
    coltype = col.type
    if isinstance(coltype, (String, Text, DateTime, JSON)):
        # SQLite 的类型亲和只是"倾向"，整数/浮点/BLOB 都能塞进 VARCHAR 列里存着
        if isinstance(value, (bytes, bytearray)):
            return "存的是 BLOB"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"存的是 {'整数' if isinstance(value, int) else '浮点数'}"
    if isinstance(coltype, (Integer, BigInteger, Float, Numeric)):
        if isinstance(value, str):
            return f"存的是文本 {value[:20]!r}"
        if isinstance(value, (bytes, bytearray)):
            return "存的是 BLOB"
    if isinstance(coltype, Boolean) and value not in (0, 1, True, False):
        return f"布尔列里存了 {value!r}"
    return None


def _parse_datetime(value: Any) -> datetime | None:
    """把 SQLite 里的时间文本解析出来；解析不了返回 None。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, int):
        # 有的行把时间当秒/毫秒整数存着，不是模型预期的文本
        return None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def canonical_value(col: Column, value: Any) -> str:
    """把一格值收成"迁移前后应当逐字节相同"的文本形式。

    P3 的搬迁脚本用同一个函数在两边算摘要，所以这里必须把方言差异抹平：SQLite 的布尔是
    0/1、时间是文本、JSON 是文本，PG 那边则是 true/false、timestamp、json。归一之后两张
    库的摘要才可以直接比。
    """
    if value is None:
        return NULL
    coltype = col.type
    if isinstance(coltype, Boolean):
        return "true" if int(value) == 1 else "false"
    if isinstance(coltype, DateTime):
        parsed = _parse_datetime(value)
        if parsed is None:
            return f"<坏时间:{value!r}>"
        if parsed.tzinfo is None:
            # SQLite 读回来不带 tzinfo，而项目写入的一律是 UTC（见 auth_service._as_utc）
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    if isinstance(coltype, JSON):
        documented: Any
        if isinstance(value, (dict, list)):
            documented = value
        else:
            try:
                documented = json.loads(value)
            except (TypeError, ValueError):
                return f"<坏JSON:{value!r}>"
        return json.dumps(documented, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if isinstance(coltype, (Integer, BigInteger, Float, Numeric)):
        return str(value)
    return str(value)


def row_text(columns: Sequence[Column], values: Mapping[str, Any]) -> str:
    """一行的规范化文本，列名一起写进去。

    审计报告和搬迁脚本各自算一次这个文本再取整表摘要，所以拼法只能有一处：列名在内，
    两张库就算列顺序不同也不会撞出同一个数。CLAUDE.md 说的"搬完在目标库上再算一遍对得上
    才算搬全"，靠的正是这两个数可比。
    """
    return "|".join(f"{col.name}={canonical_value(col, values[col.name])}" for col in columns)


def digest_rows(rows: list[str]) -> str:
    """整表内容摘要：先把每行的规范化文本收齐再排序，所以与读取顺序无关。

    搬迁脚本（``src/db_transfer.py``）在两张库上各算一遍这个数，所以它必须是个能对
    比的东西，而不是审计模块的私事。
    """
    payload = "\n".join(sorted(rows)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _db_fk_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """库里这一张表实际带外键约束的子列名。

    ``PRAGMA table_info`` 读不出外键，得用 ``foreign_key_list``；它的第 3 列（``from``）
    就是子表侧的列名。ALTER 加进来的列不会出现在这里。
    """
    return {row[3] for row in conn.execute(f'PRAGMA foreign_key_list("{table_name}")')}


def _parent_keys(conn: sqlite3.Connection, table_name: str, column: str) -> set:
    """父表某一列的全部取值，用来判孤儿行。

    这里返回的是扁平集合（不是 ``{(1,), (2,)}``），因为本模块只处理单列外键；否则子表读
    回来的裸值和元组永远比不相等，每张有外键的表都会被误报成整表孤儿。
    """
    return {row[0] for row in conn.execute(f'SELECT "{column}" FROM "{table_name}"')}


def _stream_rows(conn: sqlite3.Connection, table_name: str) -> Iterator[sqlite3.Row]:
    yield from conn.execute(f'SELECT * FROM "{table_name}"')


def _audit_table(
    conn: sqlite3.Connection,
    name: str,
    table: Table,
    db_columns: set[str],
    parent_key_cache: dict[tuple[str, str], Any],
    result: AuditResult,
) -> None:
    """一张表一趟扫描，顺手把所有检查都做完。"""
    present = [c for c in table.columns if c.name in db_columns]
    audit = TableAudit(name=name)
    row_texts: list[str] = []
    seen_samples: dict[str, int] = {}

    def report(category: str, detail: str, blocking: bool) -> None:
        key = f"{category}|{name}"
        count = seen_samples.get(key, 0)
        if count >= SAMPLES_PER_CHECK:
            if count == SAMPLES_PER_CHECK:
                result.findings.append(
                    Finding(
                        category,
                        f"{name}：同类问题还有更多，本表只列前 {SAMPLES_PER_CHECK} 条",
                        blocking,
                    )
                )
                seen_samples[key] = count + 1
            return
        seen_samples[key] = count + 1
        result.findings.append(Finding(category, detail, blocking))

    # 复合外键（两个列一起指过去）跳过：逐列单独查会误报，而当前模型里没有这种约束。
    child_columns: dict[str, tuple[str, str]] = {}
    for fk in table.foreign_keys:
        constraint = fk.constraint
        if constraint is None or len(constraint.columns) != 1:
            continue
        parent_table = fk.column.table.name
        ref_column = fk.column.name
        child_column = fk.parent.name
        if parent_table not in Base.metadata.tables or child_column not in db_columns:
            continue
        child_columns[child_column] = (parent_table, ref_column)
        cache_key = (parent_table, ref_column)
        if cache_key not in parent_key_cache:
            try:
                parent_key_cache[cache_key] = _parent_keys(conn, parent_table, ref_column)
            except sqlite3.Error:
                # 父表在这个库里根本不存在，这一列的孤儿行判不了
                parent_key_cache[cache_key] = None

    for row in _stream_rows(conn, name):
        audit.rows += 1
        for col in present:
            value = row[col.name]

            if value is None:
                if not col.nullable and col.primary_key is False and col.default is None:
                    report(
                        "not_null_violation",
                        f"{name}.{col.name} 有 NULL，但模型声明 NOT NULL",
                        True,
                    )
                continue

            violation = _is_type_violation(col, value)
            if violation:
                report("type_mismatch", f"{name}.{col.name} {violation}", True)

            if isinstance(col.type, String) and col.type.length is not None:
                text_len = len(value) if isinstance(value, str) else len(str(value))
                if text_len > col.type.length:
                    report(
                        "over_length",
                        f"{name}.{col.name} 长度 {text_len}，模型上限 {col.type.length}",
                        True,
                    )

            if isinstance(col.type, (Integer, BigInteger)):
                # PG 的 integer 是 32 位，SQLite 的 INTEGER 一律 64 位
                kind = "bigint" if isinstance(col.type, BigInteger) else "integer"
                bounds = INT64_RANGE if kind == "bigint" else INT32_RANGE
                if isinstance(value, int) and not bounds[0] <= value <= bounds[1]:
                    report(
                        "int_overflow",
                        f"{name}.{col.name} 值 {value} 超出 PG 的 {kind} 范围",
                        True,
                    )

            if isinstance(col.type, DateTime) and _parse_datetime(value) is None:
                report(
                    "bad_datetime",
                    f"{name}.{col.name} 的时间解析不了：{value!r}",
                    True,
                )

            if isinstance(col.type, JSON):
                if isinstance(value, (dict, list)):
                    pass
                else:
                    try:
                        json.loads(value)
                    except (TypeError, ValueError):
                        report(
                            "bad_json",
                            f"{name}.{col.name} 不是合法 JSON：{value!r}",
                            True,
                        )

        for column_name, (parent_table, ref_column) in child_columns.items():
            value = row[column_name]
            if value is None:
                continue
            keys = parent_key_cache.get((parent_table, ref_column))
            if keys is None:
                continue
            if value not in keys:
                report(
                    "orphan_row",
                    f"{name}.{column_name}={value!r} 在 {parent_table} 里找不到父行",
                    True,
                )

        row_texts.append(row_text(present, row))

    audit.digest = digest_rows(row_texts)
    result.tables.append(audit)


def _meaningful_rows(conn: sqlite3.Connection, table_name: str, column: str) -> int:
    """这一列里有多少行不是 NULL / 0 / 空串。

    只存在于库里的列（模型已经不要了）大多是老实现的遗留，比如全局的 ``viewed`` 和
    ``read`` 已经搬进了 ``*_reads`` 表。全是空值的话丢掉无所谓，真存了值才是丢数据，
    所以漂移报告要说清是哪一种。
    """
    row = conn.execute(
        f'SELECT COUNT(*) FROM "{table_name}" '
        f'WHERE "{column}" IS NOT NULL AND "{column}" NOT IN (0, \'\')'
    ).fetchone()
    return int(row[0])


def _audit_schema(
    conn: sqlite3.Connection,
    result: AuditResult,
    db_tables: dict[str, list[sqlite3.Row]],
) -> None:
    model_tables = {t.name: t for t in Base.metadata.tables.values()}
    for name in sorted(set(db_tables) - set(model_tables)):
        result.findings.append(
            Finding("schema_drift", f"库里的表 {name} 模型里没有：迁移会把它整个丢掉", True)
        )
    for name in sorted(set(model_tables) - set(db_tables)):
        result.findings.append(
            Finding("schema_drift", f"模型里的表 {name} 库里没有：迁移时新建（正常）", False)
        )

    for name, table in sorted(model_tables.items()):
        if name not in db_tables:
            continue
        db_columns = {row[1]: row for row in db_tables[name]}
        model_columns = {c.name for c in table.columns}
        for extra in sorted(set(db_columns) - model_columns):
            filled = _meaningful_rows(conn, name, extra)
            where = f"{name}.{extra} 只存在于库里（模型没有）"
            if filled:
                result.findings.append(
                    Finding("schema_drift", f"{where}，有 {filled} 行存了值：迁移会丢掉", True)
                )
            else:
                result.findings.append(
                    Finding("schema_drift", f"{where}，全是空值/0，丢掉不影响数据", False)
                )
        for absent in sorted(model_columns - set(db_columns)):
            result.findings.append(
                Finding(
                    "schema_drift",
                    f"{name}.{absent} 模型里有而库里没有：迁移时补列（正常）",
                    False,
                )
            )
        # SQLite 要 PRAGMA foreign_keys=ON 才强制外键，项目里没开过，所以 ALTER 加进来的
        # 归属列（favorites.user_id 那批）过去连约束都没有，孤儿行只能靠这次扫描发现。
        enforced = _db_fk_columns(conn, name)
        for column_name in sorted({c.name for c in table.columns if c.foreign_keys}):
            if column_name in db_columns and column_name not in enforced:
                result.findings.append(
                    Finding(
                        "missing_fk_constraint",
                        f"{name}.{column_name} 模型声明了外键，库里却没有这条约束",
                        False,
                    )
                )


def audit(db_path: Path) -> AuditResult:
    result = AuditResult(db_path=str(db_path))
    conn = open_read_only(db_path)
    try:
        db_tables = _db_tables(conn)
        _audit_schema(conn, result, db_tables)
        parent_key_cache: dict[tuple[str, str], set] = {}
        for name, table in sorted(Base.metadata.tables.items()):
            if name not in db_tables:
                continue
            db_columns = {row[1] for row in db_tables[name]}
            _audit_table(conn, name, table, db_columns, parent_key_cache, result)
    finally:
        conn.close()
    return result


CATEGORIES: tuple[tuple[str, str], ...] = (
    ("schema_drift", "库与模型的 schema 不一致"),
    ("missing_fk_constraint", "模型声明了外键、库里却没有约束（所以孤儿行可能存在）"),
    ("orphan_row", "孤儿行：子表有值、父表没有对应行（PG 会直接拒绝）"),
    ("type_mismatch", "列里存的值类型不对（SQLite 靠类型亲和默默收下，PG 会报错）"),
    ("over_length", "VARCHAR 超长（SQLite 不检查长度）"),
    ("int_overflow", "整数超出 PG 的 integer 范围"),
    ("not_null_violation", "NOT NULL 列里有 NULL"),
    ("bad_datetime", "日期文本解析不了"),
    ("bad_json", "JSON 列不是合法 JSON"),
)


def render_report(result: AuditResult) -> str:
    total_rows = sum(t.rows for t in result.tables)
    lines = [
        "# PG 迁移前审计",
        "",
        f"- 数据库文件：`{result.db_path}`",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 扫描的表：{len(result.tables)} 张，合计 {total_rows} 行",
        f"- **阻断项：{len(result.blocking)} 条**（🚫 每一条都会让导入失败或静默改数据）",
        "",
        "## 按类别",
        "",
    ]
    by_category: dict[str, list[Finding]] = {}
    for finding in result.findings:
        by_category.setdefault(finding.category, []).append(finding)
    for key, title in CATEGORIES:
        items = by_category.get(key, [])
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("无。")
            lines.append("")
            continue
        for item in items:
            mark = "🚫" if item.blocking else "ℹ️"
            lines.append(f"- {mark} {item.detail}")
        lines.append("")

    lines += [
        "## 各表行数与内容摘要",
        "",
        "| 表 | 行数 | 内容摘要（sha256 前 16 位） |",
        "|---|---|---|",
    ]
    for table in sorted(result.tables, key=lambda t: t.name):
        lines.append(f"| `{table.name}` | {table.rows} | `{table.digest[:16]}` |")
    lines += [
        "",
        "摘要是对每行的值做方言无关归一（布尔→true/false、时间→UTC ISO、JSON→键排序）后",
        "整表排序再哈希的结果。P3 搬完在 PG 上用同一个函数算一遍，两边一致才算搬全。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="src.db_audit", description="PG 迁移前的只读审计")
    parser.add_argument("--db", default=None, help=f"SQLite 文件路径（默认 {DEFAULT_DB}）")
    parser.add_argument(
        "--out", default=None, help="报告输出路径（默认 data/migration-audit-<日期>.md）"
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else DEFAULT_DB
    if not db_path.exists():
        print(f"db not found: {db_path}", file=sys.stderr)
        return 2

    result = audit(db_path)
    out_path = (
        Path(args.out)
        if args.out
        else db_path.parent / f"migration-audit-{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    out_path.write_text(render_report(result), encoding="utf-8")

    # 控制台是 cp936，这里只打 ASCII，中文都留在报告文件里。
    print(f"tables={len(result.tables)} rows={sum(t.rows for t in result.tables)}")
    for key, _title in CATEGORIES:
        count = sum(1 for f in result.findings if f.category == key)
        if count:
            print(f"{key}={count}")
    print(f"blocking={len(result.blocking)}")
    print(f"report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
