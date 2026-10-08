"""转码产物从此有自己的账：新增 transcode_outputs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 15:05:12.884410

这一张表记的是"某部片子的某种容器转过一份，文件写在哪儿"（#154）。产物从前只活在
`transcode_service._jobs` 那本进程内的账上，服务一重启就没有任何人知道它产出过什么，
界面上也就没有一个地方能把那份文件找回来。

`created_at` / `deleted_at` 在这里写的是 `sa.DateTime(timezone=True)`：模型那侧套了
`UTCDateTime`（#162），但它的 `impl` 就是这个类型，两种方言编译出来的 DDL 逐字节相同
——迁移脚本因此不引用应用类型，形状由 `test_utc_datetime_columns.py` 第三条用例对着
元数据核。

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('transcode_outputs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('target_format', sa.String(length=20), nullable=False),
    sa.Column('output_path', sa.String(length=1024), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('video_id', 'target_format', name='ux_transcode_output_video_format')
    )
    op.create_index(op.f('ix_transcode_outputs_video_id'), 'transcode_outputs', ['video_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_transcode_outputs_video_id'), table_name='transcode_outputs')
    op.drop_table('transcode_outputs')
