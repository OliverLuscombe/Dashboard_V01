"""add_prediction_dataset_configuration

Revision ID: 8ce03d6a5a91
Revises: 3255177d8e37
Create Date: 2026-11-16 21:45:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8ce03d6a5a91"
down_revision: Union[str, Sequence[str], None] = "3255177d8e37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist dataset classification and its prediction/date column mapping."""
    op.add_column(
        "uploaded_dataset",
        sa.Column(
            "data_type",
            sa.Text(),
            server_default=sa.text("'measurement'"),
            nullable=False,
        ),
    )
    op.add_column(
        "uploaded_dataset",
        sa.Column(
            "prediction_mapping_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove persisted prediction configuration."""
    op.drop_column("uploaded_dataset", "prediction_mapping_json")
    op.drop_column("uploaded_dataset", "data_type")
