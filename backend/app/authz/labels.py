"""Classification labels for derived items (SPEC 7.2, AGENTS.md).

A derived item (a summary, a report draft, a stored conversation turn, a
dashboard count, a correlation finding) takes the HIGHEST classification and
the UNION of the compartments of everything it was built from. This module is
the only place that rule lives; every derived item gets its label from
`Labels.derive`.

Fails closed: an input whose classification code is not in the configured
scheme cannot be labelled, so a derived item can never come out less
classified than what it was built from. An item built from no inputs at all
raises too, unless the caller says an empty item is legitimate (`empty_ok`,
e.g. a "nothing found" answer), in which case it takes the lowest configured
level, which is the honest label for content derived from no classified data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Connection


class Labelled(Protocol):
    """Anything that carries a classification and compartments (chunks, records)."""

    classification_code: str
    compartments: Any


@dataclass(frozen=True, slots=True)
class Label:
    code: str
    compartments: tuple[str, ...]


class Labels:
    """The configured classification scheme (levels and their rank order)."""

    def __init__(self, ranks: Mapping[str, int], names: Mapping[str, str] | None = None) -> None:
        if not ranks:
            raise ValueError("the classification scheme has no levels")
        self._ranks = dict(ranks)
        self._names = dict(names or {})

    @classmethod
    def load(cls, conn: Connection) -> Labels:
        rows = conn.execute(text("SELECT code, name, rank FROM classification_levels")).all()
        return cls(
            {str(row.code): int(row.rank) for row in rows},
            {str(row.code): str(row.name) for row in rows if row.name},
        )

    def display(self, code: str) -> str:
        """The level's name as the UI and documents show it, upper case (the code if unnamed)."""
        return (self._names.get(code) or code).upper()

    def rank(self, code: str) -> int | None:
        """Rank of a level, or None for a code outside the scheme."""
        return self._ranks.get(code)

    def derive(self, inputs: Iterable[Labelled], *, empty_ok: bool = False) -> Label:
        items = list(inputs)
        if not items:
            if not empty_ok:
                raise ValueError("a derived item needs at least one input to inherit a label from")
            return Label(min(self._ranks, key=self._ranks.__getitem__), ())
        unknown = {i.classification_code for i in items if i.classification_code not in self._ranks}
        if unknown:
            raise ValueError(f"unknown classification code(s): {', '.join(sorted(unknown))}")
        highest = max((i.classification_code for i in items), key=self._ranks.__getitem__)
        compartments = tuple(sorted({str(c) for i in items for c in i.compartments}))
        return Label(highest, compartments)
