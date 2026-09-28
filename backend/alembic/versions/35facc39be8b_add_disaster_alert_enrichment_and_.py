"""add disaster alert enrichment and notification dedup

Adds real-time Disaster & Weather Alert Feed enrichment on top of the
existing DisasterAdvisory model: a display title, safety instructions, and
the affected zone's centroid coordinates (for map pin placement), plus a
dedup link from Alert back to the advisory it was raised for so a tourist
is never re-notified for the same advisory on every subsequent GPS ping.

Every column is nullable, so rows created before this migration render
without the new fields rather than breaking. See services/disaster.py.

Revision ID: 35facc39be8b
Revises: 95df9a2ec560
Create Date: 2026-09-09 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35facc39be8b'
down_revision: Union[str, Sequence[str], None] = '95df9a2ec560'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("disaster_advisories") as batch:
        batch.add_column(sa.Column("title", sa.String(), nullable=True))
        batch.add_column(sa.Column("instructions", sa.Text(), nullable=True))
        batch.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Float(), nullable=True))

    with op.batch_alter_table("alerts") as batch:
        batch.add_column(sa.Column("disaster_advisory_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_alerts_disaster_advisory_id", "disaster_advisories",
            ["disaster_advisory_id"], ["id"],
        )
        batch.create_index(
            "ix_alerts_disaster_advisory_id", ["disaster_advisory_id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("alerts") as batch:
        batch.drop_index("ix_alerts_disaster_advisory_id")
        batch.drop_constraint("fk_alerts_disaster_advisory_id", type_="foreignkey")
        batch.drop_column("disaster_advisory_id")

    with op.batch_alter_table("disaster_advisories") as batch:
        batch.drop_column("longitude")
        batch.drop_column("latitude")
        batch.drop_column("instructions")
        batch.drop_column("title")
