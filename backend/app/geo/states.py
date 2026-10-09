"""The 36 states and the Federal Capital Territory: the validated set for the state filter.

A closed list, so a state parameter is checked by membership and never reaches a query
as free text. Record data carries the canonical spelling in its `state` field.
"""

from __future__ import annotations

from typing import Any

STATES: tuple[str, ...] = (
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Federal Capital Territory",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara",
    "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara",
)  # fmt: skip

_STATE_SET = frozenset(STATES)


def check_state(value: Any) -> str | None:
    """Return the canonical state name, None when not given; raise ValueError otherwise."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value not in _STATE_SET:
        raise ValueError("state must be one of the 36 states or the Federal Capital Territory")
    return value
