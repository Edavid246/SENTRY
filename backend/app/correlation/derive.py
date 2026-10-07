"""Derived-classification rule (SPEC 7.2, AGENTS.md).

A derived item (summary, finding) takes the HIGHEST classification and the
UNION of the compartments of all its inputs. One pure function, used by the
correlation job and tested directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class Labelled(Protocol):
    classification_code: str
    compartments: Any


def derive_label(inputs: Iterable[Labelled], ranks: dict[str, int]) -> tuple[str, list[str]]:
    """(classification_code, sorted compartments) for an item built from `inputs`.

    Fails closed: no inputs, or an input with an unknown classification code,
    cannot be labelled (a derived item must never come out less classified than
    what it was built from).
    """
    items = list(inputs)
    if not items:
        raise ValueError("a derived item needs at least one input to inherit a label from")
    unknown = {i.classification_code for i in items if i.classification_code not in ranks}
    if unknown:
        raise ValueError(f"unknown classification code(s): {', '.join(sorted(unknown))}")
    highest = max((i.classification_code for i in items), key=lambda code: ranks[code])
    compartments = sorted({str(c) for i in items for c in i.compartments})
    return highest, compartments
