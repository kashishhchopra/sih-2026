"""merge police network / digital tourist id with job locks / visa branch

Revision ID: 3445183755c5
Revises: 8b8e229d16f8, b3c4d5e6f7a8
Create Date: 2026-09-02 16:50:12.700076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3445183755c5'
down_revision: Union[str, Sequence[str], None] = ('8b8e229d16f8', 'b3c4d5e6f7a8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
