"""add job_locks, user FKs, sessions_valid_from

Revision ID: 9a1b2c3d4e5f
Revises: 8c173d8c1f18
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '8c173d8c1f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_locks',
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('holder', sa.String(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('job_id'),
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('sessions_valid_from', sa.DateTime(), nullable=False,
                      server_default=sa.func.now())
        )
        batch_op.create_foreign_key(
            'fk_users_tourist_id_tourists', 'tourists', ['tourist_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_users_unit_id_police_units', 'police_units', ['unit_id'], ['id']
        )
    # Drop the server_default once existing rows are backfilled -- new inserts
    # go through the ORM default (utc_now) instead.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('sessions_valid_from', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_unit_id_police_units', type_='foreignkey')
        batch_op.drop_constraint('fk_users_tourist_id_tourists', type_='foreignkey')
        batch_op.drop_column('sessions_valid_from')

    op.drop_table('job_locks')
