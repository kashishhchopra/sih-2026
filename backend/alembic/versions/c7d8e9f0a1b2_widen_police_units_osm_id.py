"""widen police_units.osm_id to BigInteger (real OSM way/relation ids can exceed 32-bit range)

Revision ID: c7d8e9f0a1b2
Revises: b2c3d4e5f6a7
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('police_units', schema=None) as batch_op:
        batch_op.alter_column(
            'osm_id',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('police_units', schema=None) as batch_op:
        batch_op.alter_column(
            'osm_id',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
