"""Findings store (SPEC 12: Finding). Classified like every other derived item."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Deterministic public id (analysis + unit): re-running the job updates in place.
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    analysis: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # Derived: highest classification and union of compartments of the evidence.
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
