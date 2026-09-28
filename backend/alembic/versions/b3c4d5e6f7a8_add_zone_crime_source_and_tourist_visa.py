"""add zone state/crime_index_source and tourist visa fields

Revision ID: b3c4d5e6f7a8
Revises: 9a1b2c3d4e5f
Create Date: 2026-09-01 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('zones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('state', sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column('crime_index_source', sa.String(), nullable=False,
                      server_default='manual')
        )

    with op.batch_alter_table('tourists', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nationality_code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('visa_type', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('visa_number', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('visa_expiry', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('passport_expiry', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('planned_states', sa.Text(), nullable=False, server_default='[]')
        )

    with op.batch_alter_table('police_units', schema=None) as batch_op:
        batch_op.add_column(sa.Column('osm_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='manual')
        )
        batch_op.create_unique_constraint('uq_police_units_osm_id', ['osm_id'])

    with op.batch_alter_table('disaster_advisories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('area_desc', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('disaster_advisories', schema=None) as batch_op:
        batch_op.drop_column('area_desc')
        batch_op.drop_column('external_id')

    with op.batch_alter_table('police_units', schema=None) as batch_op:
        batch_op.drop_constraint('uq_police_units_osm_id', type_='unique')
        batch_op.drop_column('source')
        batch_op.drop_column('osm_id')

    with op.batch_alter_table('tourists', schema=None) as batch_op:
        batch_op.drop_column('planned_states')
        batch_op.drop_column('passport_expiry')
        batch_op.drop_column('visa_expiry')
        batch_op.drop_column('visa_number')
        batch_op.drop_column('visa_type')
        batch_op.drop_column('nationality_code')

    with op.batch_alter_table('zones', schema=None) as batch_op:
        batch_op.drop_column('crime_index_source')
        batch_op.drop_column('state')
