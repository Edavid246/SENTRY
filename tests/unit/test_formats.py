"""Identifier formats: one pattern, read whole by the tools and in free text by the router."""

import pytest
from app.data_queries.formats import (
    CASE_REF,
    CONTRACT_STATUS_MENTION,
    CONTRACT_STATUSES,
    exact,
    mention,
)


def test_exact_takes_the_whole_value_and_mention_finds_a_word() -> None:
    assert exact(CASE_REF).match("FR-2026-014")
    assert not exact(CASE_REF).match("case FR-2026-014")
    found = mention(CASE_REF).search("show case fr-2026-014 please")
    assert found and found.group(1) == "fr-2026-014"
    assert not mention(CASE_REF).search("XFR-2026-014")
    assert not mention(CASE_REF, ignore_case=False).search("fr-2026-014")


@pytest.mark.parametrize("status", CONTRACT_STATUSES)
@pytest.mark.parametrize("sep", [" ", "-"])
def test_every_contract_status_reads_back_from_prose(status: str, sep: str) -> None:
    """The router turns what it found back into the tool's value the way routing.py does."""
    found = mention(CONTRACT_STATUS_MENTION).search(f"contracts {status.replace('_', sep)} now")
    assert found
    assert found.group(1).lower().replace(" ", "_").replace("-", "_") == status
