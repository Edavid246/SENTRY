"""Source adapters (SPEC 11). The core reaches source systems only through `get_adapter`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.connectors.base import SourceAdapter


def get_adapter() -> SourceAdapter:
    """The one place the source adapter is chosen (a client connector replaces it here)."""
    from app.connectors.demo import ADAPTER

    return ADAPTER
