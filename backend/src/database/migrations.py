"""启动时把库带到当前结构：Alembic 是唯一的建表出处。

库分三种，各走一条路，判断只看两件事——有没有业务表、有没有版本行，不猜数据库
类型：

* 空库（新装的 PostgreSQL，或新开的 SQLite）：跑 :func:`upgrade_head`，0001 基线
  把模型声明的表和索引一次建出来。
* 有表但没有版本行（`init_db` 时代写出来的老库）：先按
  ``session.apply_schema_fixes`` 补齐成基线的形状，再 :func:`stamp_head` 认领基线，
  于是它和新建的库从同一个版本出发。
* 已有版本行：只跑新增的修订，平时是空操作。

这里的函数都是同步的，因为它们拿到的都是 ``run_sync`` 递来的同步连接——Alembic
的脚本层只认同步连接。
"""

from pathlib import Path
from typing import Optional

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from alembic import command

#: 迁移脚本所在目录。用文件位置定位，和 uvicorn 从哪个目录启动无关。
ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"

#: Alembic 记录版本的那张表，不算业务表。
VERSION_TABLE = "alembic_version"


def _config() -> Config:
    """一份只认脚本目录的配置。

    不读 alembic.ini：``fileConfig`` 会顺手改掉全局日志，而应用要的就是「按脚本目录
    跑迁移」这一件事。连接串也不在这里，由 ``alembic/env.py`` 从应用配置取。
    """
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def _run(action: str, sync_conn: Connection, revision: str = "head") -> None:
    config = _config()
    # env.py 见到这条连接就直接用它，不再自己建引擎（见 run_migrations_online）。
    config.attributes["connection"] = sync_conn
    getattr(command, action)(config, revision)


def upgrade_head(sync_conn: Connection) -> None:
    """把库升级到最新修订；空库因此会建出全部表。"""
    _run("upgrade", sync_conn)


def stamp_head(sync_conn: Connection) -> None:
    """把当前结构登记为最新修订，不执行任何 DDL。

    只给「补齐过的老库」用：它的表已经在基线的形状上了，缺的只是版本行。
    """
    _run("stamp", sync_conn)


def current_revision(sync_conn: Connection) -> Optional[str]:
    """库里的版本行；没有版本表或表是空的都算 ``None``。"""
    return MigrationContext.configure(connection=sync_conn).get_current_revision()


def business_tables(sync_conn: Connection) -> set[str]:
    """库里已有的业务表，不含版本表。"""
    return set(inspect(sync_conn).get_table_names()) - {VERSION_TABLE}
