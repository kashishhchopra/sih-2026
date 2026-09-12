"""add safety reports, fare checks, and incident sentiment columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('safety_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tourist_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lng', sa.Float(), nullable=True),
    sa.Column('sentiment_label', sa.String(), nullable=False),
    sa.Column('sentiment_score', sa.Float(), nullable=False),
    sa.Column('urgency', sa.String(), nullable=False),
    sa.Column('distress_detected', sa.Boolean(), nullable=False),
    sa.Column('escalated_incident_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['escalated_incident_id'], ['incidents.id'], ),
    sa.ForeignKeyConstraint(['tourist_id'], ['tourists.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('safety_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_safety_reports_tourist_id'), ['tourist_id'], unique=False)

    op.create_table('fare_checks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tourist_id', sa.Integer(), nullable=False),
    sa.Column('transport_type', sa.String(), nullable=False),
    sa.Column('pickup_name', sa.String(), nullable=False),
    sa.Column('pickup_lat', sa.Float(), nullable=False),
    sa.Column('pickup_lng', sa.Float(), nullable=False),
    sa.Column('destination_name', sa.String(), nullable=False),
    sa.Column('destination_lat', sa.Float(), nullable=False),
    sa.Column('destination_lng', sa.Float(), nullable=False),
    sa.Column('distance_km', sa.Float(), nullable=False),
    sa.Column('duration_min', sa.Float(), nullable=False),
    sa.Column('estimated_min', sa.Float(), nullable=False),
    sa.Column('estimated_max', sa.Float(), nullable=False),
    sa.Column('quoted_fare', sa.Float(), nullable=False),
    sa.Column('verdict', sa.String(), nullable=False),
    sa.Column('percent_diff', sa.Float(), nullable=False),
    sa.Column('reported', sa.Boolean(), nullable=False),
    sa.Column('report_note', sa.Text(), nullable=False),
    sa.Column('reported_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tourist_id'], ['tourists.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('fare_checks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fare_checks_tourist_id'), ['tourist_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_fare_checks_transport_type'), ['transport_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_fare_checks_reported'), ['reported'], unique=False)
        batch_op.create_index(batch_op.f('ix_fare_checks_verdict'), ['verdict'], unique=False)

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sentiment_label', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('sentiment_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('distress_detected', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_column('distress_detected')
        batch_op.drop_column('sentiment_score')
        batch_op.drop_column('sentiment_label')

    with op.batch_alter_table('fare_checks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fare_checks_verdict'))
        batch_op.drop_index(batch_op.f('ix_fare_checks_reported'))
        batch_op.drop_index(batch_op.f('ix_fare_checks_transport_type'))
        batch_op.drop_index(batch_op.f('ix_fare_checks_tourist_id'))
    op.drop_table('fare_checks')

    with op.batch_alter_table('safety_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_safety_reports_tourist_id'))
    op.drop_table('safety_reports')
