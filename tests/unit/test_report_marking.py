"""Both reports print the marking the same way: the level as the UI names it, never the code."""

from __future__ import annotations

from app.authz.labels import Label, Labels
from app.data_queries.tools import ToolResult
from app.reporting.marking import DRAFT_BANNER, marking
from app.reporting.training import generate_training_report

LABELS = Labels(
    {"restricted": 1, "secret": 3}, {"restricted": "Internal", "secret": "Government-sensitive"}
)


def test_marking_line() -> None:
    assert marking("Confidential", ("CLIENT-C",)) == "CONFIDENTIAL (CLIENT-C)"
    assert marking("Internal", []) == "INTERNAL"


def test_training_draft_names_the_level_as_the_ui_does() -> None:
    empty = ToolResult(tool="training_activity", params={}, columns=(), rows=[], records=())
    report = generate_training_report(
        "training summary",
        empty,
        [],
        Label("secret", ("CLIENT-A", "UAS-OPS")),
        labels=LABELS,
        gateway=None,  # type: ignore[arg-type]  # nothing to draft over, so no model call
    )
    banner, line = report.text.splitlines()[:2]
    assert banner == DRAFT_BANNER
    assert line == "Classification: GOVERNMENT-SENSITIVE (CLIENT-A, UAS-OPS)"
