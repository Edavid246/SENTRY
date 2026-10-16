"""Assistant models: conversations and their messages (SPEC 10.1).

Each row carries the derived label it was stored under, like every other derived item. The
reads and writes are in `app.assistant.conversations`.
"""

from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="Conversation")
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    classification_code: Mapped[str] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=False
    )
    compartments: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
