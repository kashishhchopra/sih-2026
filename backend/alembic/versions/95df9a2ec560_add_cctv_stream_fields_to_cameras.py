"""add cctv stream fields to cameras

Adds an optional real video feed to the existing camera directory. Every
column is nullable or has a server_default, so rows registered before this
migration stay valid: they simply have no stream and render as a coverage
record with no viewable feed.

Revision ID: 95df9a2ec560
Revises: 811145802bc1
Create Date: 2026-09-09 16:03:14.667651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95df9a2ec560'
down_revision: Union[str, Sequence[str], None] = '811145802bc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("cameras") as batch:
        batch.add_column(sa.Column("stream_url", sa.String(), nullable=True))
        batch.add_column(sa.Column(
            "stream_type", sa.String(), nullable=False, server_default="none"))
        batch.add_column(sa.Column(
            "feed_source", sa.String(), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("source_url", sa.String(), nullable=True))
        batch.add_column(sa.Column("attribution", sa.String(), nullable=True))
        batch.add_column(sa.Column("assigned_station_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("stream_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("stream_checked_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_cameras_assigned_station_id", "police_stations",
            ["assigned_station_id"], ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint("fk_cameras_assigned_station_id", type_="foreignkey")
        batch.drop_column("stream_checked_at")
        batch.drop_column("stream_status")
        batch.drop_column("assigned_station_id")
        batch.drop_column("attribution")
        batch.drop_column("source_url")
        batch.drop_column("feed_source")
        batch.drop_column("stream_type")
        batch.drop_column("stream_url")
