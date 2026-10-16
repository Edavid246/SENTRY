"""What every report carries, whichever report it is: the DRAFT banner and the marking line.

Both are added by code, never by a model or a renderer (the assistant informs, humans decide;
AGENTS.md "derived items").
"""

from __future__ import annotations

DRAFT_BANNER = "DRAFT FOR HUMAN REVIEW - not an approved document"


def marking(name: str, compartments: tuple[str, ...] | list[str]) -> str:
    """The marking line: CLASSIFICATION (COMPARTMENT, COMPARTMENT), the level as the UI names it."""
    return name.upper() + (f" ({', '.join(compartments)})" if compartments else "")
