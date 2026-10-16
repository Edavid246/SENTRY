"""The derived-classification rule (SPEC 7.2): highest classification, union of compartments."""

import pytest
from app.authz.labels import Label, Labels

LABELS = Labels({"unclassified": 0, "restricted": 1, "confidential": 2, "secret": 3})


def Item(code: str, compartments: tuple[str, ...] = ()) -> Label:
    """A Label is itself Labelled, so it stands in for any labelled input."""
    return Label(code, compartments)


def test_highest_classification_and_union_of_compartments() -> None:
    label = LABELS.derive(
        [
            Item("restricted"),
            Item("confidential", ("UAS-OPS",)),
            Item("restricted", ("FORENSICS",)),
            Item("confidential", ("UAS-OPS", "FORENSICS")),
        ]
    )
    assert label == Label("confidential", ("FORENSICS", "UAS-OPS"))


def test_never_less_classified_than_any_input_whatever_the_order() -> None:
    items = [Item("unclassified"), Item("secret", ("UAS-OPS",)), Item("restricted")]
    for ordered in (items, items[::-1], [items[1], items[0], items[2]]):
        assert LABELS.derive(ordered) == Label("secret", ("UAS-OPS",))


def test_fails_closed() -> None:
    with pytest.raises(ValueError):
        LABELS.derive([])
    with pytest.raises(ValueError):
        LABELS.derive([Item("restricted"), Item("top-secret")])
    with pytest.raises(ValueError):  # an unknown code fails closed even when empty is allowed
        LABELS.derive([Item("top-secret")], empty_ok=True)


def test_empty_item_takes_the_lowest_configured_level_when_allowed() -> None:
    assert LABELS.derive([], empty_ok=True) == Label("unclassified", ())
    assert Labels({"official": 5, "sensitive": 9}).derive([], empty_ok=True).code == "official"


def test_display_uses_the_ui_name_and_never_prints_none() -> None:
    labels = Labels({"secret": 3, "open": 1}, {"secret": "Government-sensitive", "open": None})  # type: ignore[dict-item]
    assert labels.display("secret") == "GOVERNMENT-SENSITIVE"
    assert labels.display("open") == "OPEN"  # a missing name falls back to the code
    assert labels.display("unlisted") == "UNLISTED"


def test_a_derived_label_is_an_input_to_the_next_derivation() -> None:
    report = LABELS.derive([Item("restricted", ("UAS-OPS",))])
    assert report.classification_code == "restricted"
    assert LABELS.derive([report, Item("confidential", ("FORENSICS",))]) == Label(
        "confidential", ("FORENSICS", "UAS-OPS")
    )
