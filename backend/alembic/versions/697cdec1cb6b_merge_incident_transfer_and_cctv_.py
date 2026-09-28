"""merge incident-transfer and cctv/disaster-alert branches

Revision ID: 697cdec1cb6b
Revises: 29981ad927dd, 35facc39be8b
Create Date: 2026-09-10 01:40:49.702947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '697cdec1cb6b'
down_revision: Union[str, Sequence[str], None] = ('29981ad927dd', '35facc39be8b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
