"""Identity, classification and unit models (SPEC 7, 12)."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ClassificationLevel(Base):
    __tablename__ = "classification_levels"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


class Compartment(Base):
    __tablename__ = "compartments"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255))


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    clearance_code: Mapped[str | None] = mapped_column(
        ForeignKey("classification_levels.code"), nullable=True
    )
    keycloak_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    data_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserCompartment(Base):
    __tablename__ = "user_compartments"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    compartment_code: Mapped[str] = mapped_column(ForeignKey("compartments.code"), primary_key=True)
