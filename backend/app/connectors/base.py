"""Adapter contract (SPEC 11.1): the only way the core reaches a source system.

describe/search/get/stream/sync, all read-only; there is no write(). Every
record an adapter returns carries source system, source record id, retrieval
time, classification, compartments and owning unit (SPEC 11.1). The core
imports this module, never a concrete adapter's storage.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from app.authz.context import AccessContext
from app.authz.scope import Scope


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One canonical record in the form every adapter returns."""

    source_ref: str
    entity_type: str
    source_system: str
    data: dict[str, Any]
    classification_code: str
    compartments: tuple[str, ...]
    unit_path: str
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class RecordFilter:
    """Typed search criteria. Everything here is a bound parameter downstream.

    `entity_type` None means every type; `unit_path` selects that unit and
    everything below it; `date_field` names
    an allow-listed ISO-date field of the record, kept when its value is on or
    before `on_or_before`.
    """

    entity_type: str | None = None
    unit_path: str | None = None
    date_field: str | None = None
    on_or_before: date | None = None


@dataclass(frozen=True, slots=True)
class AdapterDescription:
    name: str
    entity_types: tuple[str, ...]
    read_only: bool = True
    health: str = "connected"
    notes: tuple[str, ...] = field(default_factory=tuple)


class SourceAdapter(Protocol):
    def describe(self) -> AdapterDescription: ...

    def search(self, scope: Scope, record_filter: RecordFilter) -> list[SourceRecord]: ...

    def get(self, scope: Scope, source_ref: str) -> SourceRecord | None: ...

    def stream(self, scope: Scope, since: datetime) -> Iterator[SourceRecord]: ...

    def sync(self, ctx: AccessContext) -> int: ...
