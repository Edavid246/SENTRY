"""Knowledge-pathway models: documents and retrieval chunks (SPEC 12)."""

from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Embedding dimension comes from config (BGE-M3, 1024) — see Settings.embedding_dim.
EMBEDDING_DIM = 1024


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    source_system_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_systems.id"), nullable=True
    )
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL until the knowledge slice embeds it; exact search (no HNSW) — docs/STUBS.md.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Denormalised classification of the parent document (invariant-tested in seed tests).
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
