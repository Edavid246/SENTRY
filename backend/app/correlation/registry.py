"""The correlation analyses a run executes, in order."""

from __future__ import annotations

from collections.abc import Callable

from app.authz.labels import Labels
from app.authz.scope import Scope
from app.correlation import analysis, custody, qc_delivery
from app.correlation.types import FindingDraft

Analysis = Callable[[Scope, Labels, dict[str, str]], list[FindingDraft]]

ANALYSES: dict[str, Analysis] = {
    analysis.ANALYSIS: analysis.run_rising_faults,
    custody.ANALYSIS: custody.run_repeated_custody_gaps,
    qc_delivery.ANALYSIS: qc_delivery.run_qc_hold_overdue_delivery,
}


def run_all(scope: Scope, labels: Labels, names: dict[str, str]) -> list[FindingDraft]:
    return [d for run in ANALYSES.values() for d in run(scope, labels, names)]
