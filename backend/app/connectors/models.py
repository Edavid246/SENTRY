"""Connector models: source systems and canonical records (SPEC 11, 12)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SourceSystem(Base):
    __tablename__ = "source_systems"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    default_classification: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="connected")


class CanonicalRecord(Base):
    __tablename__ = "canonical_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system_id: Mapped[UUID] = mapped_column(ForeignKey("source_systems.id"), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
