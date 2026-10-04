# tests/test_migrations.py
"""Alembic 接管 schema 之后的三条启动路线。

``init_db`` 从此只认库、选路，建表的事全在 ``alembic/versions`` 里。这里守住三件事：
空库由 0001 基线建出、而且建出来的形状和模型声明的一字不差；有表却没版本行的老库
会被认出来、补齐后 stamp 到基线；已经版本化的库再跑一次是空操作。
"""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

import src.models  # noqa: F401  # 让每个模型都注册进 Base.metadata
from src.database.base import Base
from src.database.migrations import (
    ALEMBIC_DIR,
    business_tables,
    current_revision,
    stamp_head,
    upgrade_head,
)
from src.database.session import _is_unversioned_legacy


def _head() -> str:
    return ScriptDirectory(str(ALEMBIC_DIR)).get_current_head()


def _engine(tmp_path):
    """一个独立的文件库：这几条路线都要碰到真实存在的表，内存库活不过连接。"""
    return create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")


def _shape(conn):
    """autogenerate 的差异清单，空列表意味着库和模型声明完全对得上。"""
    return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def test_empty_database_is_born_from_the_baseline(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        upgrade_head(conn)

        assert business_tables(conn) == set(Base.metadata.tables)
        assert current_revision(conn) == _head()
    engine.dispose()


def test_the_baseline_describes_the_models_exactly(tmp_path):
    """模型加了列却忘了写修订时，这一条要变红。"""
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        upgrade_head(conn)
        assert _shape(conn) == []
    engine.dispose()


def test_the_route_is_chosen_by_tables_and_version_row(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        assert not _is_unversioned_legacy(conn)  # 空库：走基线

        Base.metadata.create_all(conn)
        assert _is_unversioned_legacy(conn)  # 老库：有表、无版本行

        stamp_head(conn)
        assert not _is_unversioned_legacy(conn)  # 认领过：走常规升级
    engine.dispose()


def test_a_legacy_database_lands_on_the_same_shape_as_a_fresh_one(tmp_path):
    """补齐过的老库 stamp 之后，必须和新建的库站在同一个版本、同一个形状上。"""
    legacy = _engine(tmp_path)
    with legacy.begin() as conn:
        Base.metadata.create_all(conn)  # 修复后的老库：表齐、没有版本行
        stamp_head(conn)

        assert current_revision(conn) == _head()
        assert _shape(conn) == []

        upgrade_head(conn)  # 认领过之后，再启动是空操作
        assert current_revision(conn) == _head()
    legacy.dispose()


def test_stamp_registers_the_version_without_touching_tables(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        before = business_tables(conn)

        stamp_head(conn)

        assert business_tables(conn) == before
        rows = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()
        assert rows == [_head()]
    engine.dispose()
