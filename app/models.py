import reflex as rx
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UploadedDataset(Base):
    """Publicly shared CSV metadata; column_names_json stores an ordered JSON array."""

    __tablename__ = "uploaded_dataset"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="ck_uploaded_dataset_row_count"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        Text, default="", server_default=text("''")
    )
    original_filename: Mapped[str] = mapped_column(
        Text, default="", server_default=text("''")
    )
    column_names_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default=text("'[]'")
    )
    row_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    source: Mapped[str] = mapped_column(
        Text, default="uploaded_csv", server_default=text("'uploaded_csv'")
    )
    status: Mapped[str] = mapped_column(
        Text, default="pending", server_default=text("'pending'")
    )
    overview_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    overview_mapping_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default=text("'{}'")
    )


class UploadedDatasetRow(Base):
    """Editable cells stored as a JSON array matching the dataset's column order."""

    __tablename__ = "uploaded_dataset_row"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "row_position",
            name="uq_uploaded_dataset_row_position",
        ),
        CheckConstraint(
            "row_position >= 0", name="ck_uploaded_dataset_row_position"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_dataset.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        default=None,
    )
    row_position: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    cell_values_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default=text("'[]'")
    )
