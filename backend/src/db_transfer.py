"""把老库的数据搬进新库：一次事务、按外键顺序、搬完当场对账。

前提是新库的表已经由 Alembic 建好（连上它启动一次 ``init_db`` 即可，见
``src/database/migrations.py``）。这个脚本不建表、不改表，只搬行，所以它对 schema
的唯一要求是"和模型声明一致"。

搬完立刻比摘要，而不是"跑起来看看"：两边都按模型的列声明读回来，用
``db_audit.row_text`` 收成同一种文本（列名也在内，所以和审计报告里的数可比），再整表
排序取哈希。布尔在 SQLite 是 0/1、PG 是 true/false，时间在 SQLite 是无偏移文本、PG 是
timestamptz——归一之后才谈得上逐字节相同。对不上就整笔回滚：宁可什么也没搬，也不要搬一半。

命令行输出保持 ASCII：控制台是 cp936，中文报表会花掉。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Table, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

import src.models  # noqa: F401  # 只为把全部模型注册进 Base.metadata
from src.config import BACKEND_ROOT, settings
from src.database.base import Base
from src.db_audit import digest_rows, row_text
from src.utils.time import as_utc

# 会话不搬。旧 token 到了新库还能登进去，等于换了锁却没换钥匙；让人重登一次的成本，
# 比带着可能被抄走的凭据换库低得多。
SKIP_TABLES = frozenset({"sessions"})

#: 版本行跟着目标库自己的 schema 走，不搬。
VERSION_TABLE = "alembic_version"

DEFAULT_SOURCE = f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'data' / 'videos.db').as_posix()}"

# 这几类都算"这一行没存过任何东西"，丢在老库里不值得报警。
_BLANK = (None, 0, "", False)


@dataclass
class TableMove:
    name: str
    rows: int = 0
    dropped_columns: dict[str, int] = field(default_factory=dict)
    source_digest: str = ""
    target_digest: str = ""

    @property
    def matches(self) -> bool:
        return self.source_digest == self.target_digest


@dataclass
class TransferReport:
    moves: list[TableMove] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rolled_back: bool = False

    @property
    def total_rows(self) -> int:
        return sum(move.rows for move in self.moves)

    def by_name(self, name: str) -> TableMove:
        for move in self.moves:
            if move.name == name:
                return move
        raise KeyError(name)


class TransferError(Exception):
    """搬不成。抛出时事务还没提交，新库回到动手前的样子。"""


class _Rollback(Exception):
    """演练用：检查和对账全过了，仍然主动把事务退出去。"""


def _model_tables() -> list[Table]:
    """按外键拓扑序排好的业务表：父表一定在子表之前插进去。"""
    return [t for t in Base.metadata.sorted_tables if t.name not in SKIP_TABLES]


def _table_names(sync_conn: Connection) -> set[str]:
    return set(inspect(sync_conn).get_table_names())


def _column_names(sync_conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in inspect(sync_conn).get_columns(table)}


async def _read(conn: AsyncConnection, table: Table) -> list[dict[str, Any]]:
    """按模型的列声明读一张表，时间一律收成带 UTC 时区的时刻。

    走 ``select(table)`` 而不是裸 ``SELECT *``：JSON 与时间列要经过模型声明的类型，
    否则 SQLite 原样吐出字符串，插到 PG 那边就成了"把 JSON 存成一串文本"。

    补时区不是为了好看：SQLite 读回来的 ``datetime`` 永远不带 tzinfo，而 asyncpg 碰到
    不带 tzinfo 的值是按**数据库会话时区**理解的，于是 UTC 的时刻插进 ``timestamptz``
    会整体偏移（本机 +8 就早 8 小时）。不报错、摘要也对不上，是最难发现的一类搬错。
    """
    result = await conn.execute(select(table))
    return [
        {key: as_utc(value) if isinstance(value, datetime) else value for key, value in row.items()}
        for row in result.mappings()
    ]


async def _dropped_columns(conn: AsyncConnection, table: Table) -> dict[str, int]:
    """库里存着、模型已不再声明的列，以及其中真有值的行数。

    典型是 ``new_videos.viewed`` 与 ``notifications.read``：M2 把"读过没"翻成了两张
    ``_reads`` 表的行，老列留在库里没删。值全空就说明丢掉不影响任何人。
    """
    declared = {c.name for c in table.columns}
    actual = await conn.run_sync(_column_names, table.name)
    counts: dict[str, int] = {}
    for column in sorted(actual - declared):
        rows = await conn.execute(text(f'SELECT "{column}" FROM "{table.name}"'))
        counts[column] = sum(1 for (value,) in rows if value not in _BLANK)
    return counts


def _missing_columns(table: Table, columns: set[str]) -> list[str]:
    return [c.name for c in table.columns if c.name not in columns]


def _null_in_required(table: Table, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """非空列里留着 NULL 的行：新库会直接拒收。

    归属列在老库里是 SQLite ``ADD COLUMN`` 加出来的可空列，正常情况下第一个 owner
    已经把它们认领完了；还有 NULL 就说明认领没跑过，得先在老库上启动一次应用。
    """
    problems: list[str] = []
    for column in table.columns:
        if column.nullable:
            continue
        bad = [row.get("id") for row in rows if row.get(column.name) is None]
        if bad:
            shown = ", ".join(str(i) for i in bad[:5])
            problems.append(
                f"{table.name}.{column.name}: {len(bad)} 行是 NULL，但新库要求非空（id: {shown}）"
            )
    return problems


def _orphans(
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    every: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """外键指向的行不在：SQLite 默认不拦，PG 会把整笔事务一起拒掉。"""
    problems: list[str] = []
    for column in table.columns:
        for fk in column.foreign_keys:
            parent_column = fk.column  # 注意 parent 是子列这边，被引用的列叫 column
            parent_rows = every.get(parent_column.table.name)
            if parent_rows is None:
                continue  # 父表压根不在这次搬运范围内（sessions）
            keys = {row[parent_column.name] for row in parent_rows}
            bad = [
                row.get("id")
                for row in rows
                if row.get(column.name) is not None and row.get(column.name) not in keys
            ]
            if bad:
                shown = ", ".join(str(i) for i in bad[:5])
                problems.append(
                    f"{table.name}.{column.name}: {len(bad)} 行在 {parent_column.table.name} "
                    f"里找不到父行（id: {shown}）"
                )
    return problems


async def _reset_sequences(
    conn: AsyncConnection, table: Table, rows: Sequence[Mapping[str, Any]]
) -> None:
    """显式插过主键之后，把自增计数器拨到最大值往后。

    不拨的话，新库的第一条插入会撞上搬过来的 id：PG 直接报主键冲突，SQLite 则把
    冲突留到下一条写入。复合主键的表（``video_tags``、两张 ``_reads``）没有序列可拨。
    """
    if not rows:
        return
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        return
    pk = pk_columns[0]
    if pk.autoincrement is False or not issubclass(pk.type.python_type, int):
        return
    highest = max(row[pk.name] for row in rows)
    if conn.dialect.name == "postgresql":
        # 不是标识列的（比如 user_preferences 那种"主键即外键"）问不出序列名，
        # pg_get_serial_sequence 给 NULL，就用 WHERE 把它筛掉而不是另加一层判断。
        await conn.execute(
            text(
                "SELECT setval(seq, :v) FROM "
                "(SELECT pg_get_serial_sequence(:t, :c) AS seq) named "
                "WHERE named.seq IS NOT NULL"
            ),
            {"t": table.name, "c": pk.name, "v": highest},
        )
    elif conn.dialect.name == "sqlite" and pk.autoincrement is True:
        if "sqlite_sequence" in await conn.run_sync(_table_names):
            await conn.execute(
                text("INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (:n, :s)"),
                {"n": table.name, "s": highest},
            )


def _digest(rows: Sequence[Mapping[str, Any]], table: Table) -> str:
    return digest_rows([row_text(table.columns, row) for row in rows])


async def _check_source(source: AsyncConnection, tables: Sequence[Table]) -> list[str]:
    """老库必须表齐列齐：缺的就是还没在新版本上启动过，先启动再来搬。

    返回老库里有、但这次不在搬运范围内的表名（``alembic_version`` 除外）。
    """
    actual = await source.run_sync(_table_names)
    for table in tables:
        if table.name not in actual:
            raise TransferError(
                f"老库缺表 {table.name}：先把应用在新版本上启动一次，让它建齐并补齐"
            )
        columns = await source.run_sync(_column_names, table.name)
        missing = _missing_columns(table, columns)
        if missing:
            raise TransferError(
                f"老库 {table.name} 缺列 {missing}：先把应用在新版本上启动一次，"
                "让补齐 SQL 跑完，再搬"
            )
    return sorted(actual - {t.name for t in tables} - {VERSION_TABLE})


async def _check_target_is_empty(target: AsyncConnection, tables: Sequence[Table]) -> None:
    """新库必须是空的：半路重跑会把同一批行插两遍，摘要对不上还是小事。"""
    for table in tables:
        count = (
            await target.execute(text(f'SELECT COUNT(*) FROM "{table.name}"'))
        ).scalar_one()
        if count:
            raise TransferError(
                f"新库的 {table.name} 已经有 {count} 行。要么先清干净（PG 上 "
                "DROP SCHEMA public CASCADE 再启动一次应用），要么别重复搬"
            )


async def transfer(source_url: str, target_url: str, *, dry_run: bool = False) -> TransferReport:
    """把 ``source_url`` 的行搬进 ``target_url``，全程一条事务。"""
    report = TransferReport()
    source_engine = create_async_engine(source_url)
    target_engine = create_async_engine(target_url)
    tables = _model_tables()
    try:
        async with source_engine.connect() as source:
            leftover = await _check_source(source, tables)
            if leftover:
                report.warnings.append(f"老库里的 {leftover} 不在搬运范围内，留在原库")
            data = {table.name: await _read(source, table) for table in tables}

            blockers: list[str] = []
            for table in tables:
                rows = data[table.name]
                move = TableMove(
                    name=table.name,
                    rows=len(rows),
                    dropped_columns=await _dropped_columns(source, table),
                    source_digest=_digest(rows, table),
                )
                report.moves.append(move)
                blockers.extend(_null_in_required(table, rows))
                blockers.extend(_orphans(table, rows, data))
                for column, filled in move.dropped_columns.items():
                    if filled:
                        report.warnings.append(
                            f"{table.name}.{column} 只在老库里存在，{filled} 行存过值；"
                            "模型已经不再用它，搬过去会丢"
                        )
            if blockers:
                raise TransferError(
                    "老库里有新库收不下的行，先处理完再搬：\n  " + "\n  ".join(blockers)
                )

        async with target_engine.begin() as target:
            await _check_target_is_empty(target, tables)
            for table in tables:
                rows = data[table.name]
                if rows:
                    await target.execute(table.insert(), [dict(row) for row in rows])
                await _reset_sequences(target, table, rows)

            # 对账在提交之前：读回来的是这张事务里的数据，对不上就整体回滚。
            for table in tables:
                report.by_name(table.name).target_digest = _digest(
                    await _read(target, table), table
                )
            mismatched = [move.name for move in report.moves if not move.matches]
            if mismatched:
                raise TransferError(
                    "这些表在新库读回来的内容和老库不一致：" + ", ".join(mismatched)
                )
            if dry_run:
                raise _Rollback()
    except _Rollback:
        report.rolled_back = True
    finally:
        await source_engine.dispose()
        await target_engine.dispose()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把老库的行搬进已经建好表的新库")
    parser.add_argument("--from", dest="source", default=DEFAULT_SOURCE, help="老库连接串")
    parser.add_argument(
        "--to", dest="target", default=settings.database_url, help="新库连接串（默认取应用配置）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="一路跑到对账通过，然后回滚，新库不留一行"
    )
    args = parser.parse_args(argv)

    try:
        report = asyncio.run(transfer(args.source, args.target, dry_run=args.dry_run))
    except TransferError as error:
        print(f"ABORTED: {error}", file=sys.stderr)
        return 1

    for warning in report.warnings:
        print(f"WARN  {warning}")
    for move in report.moves:
        state = "OK" if move.matches else "MISMATCH"
        print(f"{move.name:<22} rows={move.rows:<7} digest={state}")
    print(f"total rows: {report.total_rows}")
    print("dry-run: rolled back, nothing written" if report.rolled_back else "committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
