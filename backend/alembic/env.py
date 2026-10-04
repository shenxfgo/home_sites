"""Alembic 的运行环境。

这个项目的迁移由 ``init_db()`` 在启动时驱动（见 ``src/database/migrations.py``），
所以这里既要能被 CLI 调用，也要能被应用以编程方式调用；两条路都从
``src.config.settings.database_url`` 取连接串，配置文件里不再放第二份口令。
"""

from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import src.models  # noqa: F401  # 导入即注册，autogenerate 才能看到全部表
from alembic import context
from src.config import settings
from src.database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串只认应用配置这一个出处。alembic.ini 里不留 sqlalchemy.url，
# 免得口令在两个地方各活一份。ini 的值要过一遍 ConfigParser 的插值，所以连接串里
# 出现的 ``%``（口令里完全合法）得先成对写，否则读出来就是另一个值。
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """``alembic upgrade head --sql``：只把 SQL 打到标准输出，不碰数据库。"""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """把 Alembic 配好后跑一遍当前要执行的迁移。

    ``connection`` 既可能是 CLI 经 ``run_sync`` 递来的同步连接，也可能是应用启动时
    递来的那条（见 ``src/database/migrations.py``），所以这里不碰 asyncio。
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table="alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """连真库跑迁移。

    应用启动时（``src/database/migrations.py``）已经自己开着一条连接在跑，那条连接
    经 ``config.attributes`` 递进来，这里直接用它——此时事件循环正在转，再调
    ``asyncio.run`` 就是嵌套循环。命令行没有现成连接，才自己建一个异步引擎。
    """
    injected = config.attributes.get("connection")
    if injected is not None:
        _do_run_migrations(injected)
        return

    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
