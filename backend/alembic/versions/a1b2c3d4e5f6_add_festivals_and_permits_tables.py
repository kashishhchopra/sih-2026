"""add festivals and permits tables

Revision ID: a1b2c3d4e5f6
Revises: 697cdec1cb6b
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '697cdec1cb6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('festivals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('state', sa.String(), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lng', sa.Float(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('recurring_yearly', sa.Boolean(), nullable=False),
    sa.Column('crowd_impact', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('festivals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_festivals_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_festivals_start_date'), ['start_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_festivals_state'), ['state'], unique=False)

    op.create_table('permits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tourist_id', sa.Integer(), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=True),
    sa.Column('permit_type', sa.String(), nullable=False),
    sa.Column('destination_name', sa.String(), nullable=False),
    sa.Column('form_json', sa.Text(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('reference_no', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('decided_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tourist_id'], ['tourists.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('permits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permits_tourist_id'), ['tourist_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_permits_permit_type'), ['permit_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_permits_status'), ['status'], unique=False)
        batch_op.create_unique_constraint(batch_op.f('uq_permits_reference_no'), ['reference_no'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('permits', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_permits_reference_no'), type_='unique')
        batch_op.drop_index(batch_op.f('ix_permits_status'))
        batch_op.drop_index(batch_op.f('ix_permits_permit_type'))
        batch_op.drop_index(batch_op.f('ix_permits_tourist_id'))
    op.drop_table('permits')

    with op.batch_alter_table('festivals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_festivals_state'))
        batch_op.drop_index(batch_op.f('ix_festivals_start_date'))
        batch_op.drop_index(batch_op.f('ix_festivals_category'))
    op.drop_table('festivals')
