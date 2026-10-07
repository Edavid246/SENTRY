"""The derived-classification rule (SPEC 7.2): highest classification, union of compartments."""

from dataclasses import dataclass

import pytest
from app.correlation.derive import derive_label

RANKS = {"unclassified": 0, "restricted": 1, "confidential": 2, "secret": 3}


@dataclass
class Item:
    classification_code: str
    compartments: tuple[str, ...] = ()


def test_highest_classification_and_union_of_compartments() -> None:
    code, compartments = derive_label(
        [
            Item("restricted"),
            Item("confidential", ("UAS-OPS",)),
            Item("restricted", ("FORENSICS",)),
            Item("confidential", ("UAS-OPS", "FORENSICS")),
        ],
        RANKS,
    )
    assert code == "confidential"
    assert compartments == ["FORENSICS", "UAS-OPS"]


def test_one_secret_input_makes_the_whole_item_secret() -> None:
    inputs = [Item("restricted")] * 9 + [Item("secret")]
    assert derive_label(inputs, RANKS) == ("secret", [])


def test_never_less_classified_than_any_input_whatever_the_order() -> None:
    items = [Item("unclassified"), Item("secret", ("UAS-OPS",)), Item("restricted")]
    for ordered in (items, items[::-1], [items[1], items[0], items[2]]):
        assert derive_label(ordered, RANKS) == ("secret", ["UAS-OPS"])


def test_fails_closed() -> None:
    with pytest.raises(ValueError):
        derive_label([], RANKS)
    with pytest.raises(ValueError):
        derive_label([Item("restricted"), Item("top-secret")], RANKS)
