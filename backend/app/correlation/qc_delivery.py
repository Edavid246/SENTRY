"""Correlation: a production run on QC hold sits behind an overdue delivery.

Rule, per production run the caller can see: the run is on QC hold, AND a delivery in the same
unit is overdue for the same product. The contract behind that delivery is attached as evidence
(with its status) so the owner sees what is at stake. The inputs come from the audited typed
tools `production_qc_holds`, `deliveries_overdue` and `contracts_status`, so the finding can only
be built from rows its runner was cleared for and inherits their highest classification and the
union of their compartments.

The product is matched by name: the delivery item must contain the run's product, case
insensitively ("Helmet liner" in "Helmet liner lot"). A held run with no overdue delivery for its
product, or an overdue delivery whose run was released, produces nothing.

The summary is deterministic text built from the numbers; no model writes it.
"""

from __future__ import annotations

from app.authz.labels import Labels
from app.authz.scope import Scope
from app.clock import demo_today
from app.connectors.base import SourceRecord
from app.correlation.types import FindingDraft
from app.data_queries.registry import execute_tool

ANALYSIS = "qc_hold_overdue_delivery"


def run_qc_hold_overdue_delivery(
    scope: Scope, labels: Labels, names: dict[str, str]
) -> list[FindingDraft]:
    root = scope.ctx.unit_path
    holds = execute_tool(scope, "production_qc_holds", {"unit_path": root}).records
    late = execute_tool(scope, "deliveries_overdue", {"unit_path": root}).records
    contracts = {
        str(c.data["contract_ref"]): c
        for c in execute_tool(scope, "contracts_status", {"unit_path": root}).records
    }

    drafts: list[FindingDraft] = []
    for run in sorted(holds, key=lambda r: str(r.data["run_ref"])):
        product = str(run.data["product"]).lower()
        deliveries = [
            d
            for d in late
            if d.unit_path == run.unit_path and product in str(d.data["item"]).lower()
        ]
        if not deliveries:
            continue
        linked: list[SourceRecord] = [
            contracts[ref]
            for ref in sorted({str(d.data["contract_ref"]) for d in deliveries})
            if ref in contracts
        ]
        evidence = [run, *deliveries, *linked]
        label = labels.derive(evidence)
        unit_name = names.get(run.unit_path, run.unit_path)
        run_ref = str(run.data["run_ref"])
        refs = [str(d.data["delivery_ref"]) for d in deliveries]
        drafts.append(
            FindingDraft(
                key=f"FND-QC-HOLD-OVERDUE-{run_ref}",
                analysis=ANALYSIS,
                title=f"{unit_name}: QC hold on {run.data['product']} is holding up an "
                "overdue delivery",
                summary=(
                    f"Production run {run_ref} ({run.data['product']}) is on QC hold: "
                    f"{run.data['hold_reason']}. "
                    + (
                        f"Overdue delivery {refs[0]} for the same product cannot"
                        if len(refs) == 1
                        else f"{len(refs)} overdue deliveries for the same product "
                        f"({', '.join(refs)}) cannot"
                    )
                    + " be fulfilled until the run is released."
                    + (
                        " Contract status: "
                        + ", ".join(
                            f"{c.data['contract_ref']} {str(c.data['status']).replace('_', ' ')}"
                            for c in linked
                        )
                        + "."
                        if linked
                        else ""
                    )
                ),
                severity="high",
                classification_code=label.code,
                compartments=list(label.compartments),
                unit_path=run.unit_path,
                evidence_ids=sorted(r.source_ref for r in evidence),
                details={
                    "rule": (
                        "a production run on QC hold and an overdue delivery for the same "
                        "product in the same unit"
                    ),
                    "as_of": demo_today().isoformat(),
                    "run_ref": run_ref,
                    "product": run.data["product"],
                    "hold_reason": run.data["hold_reason"],
                    "overdue_deliveries": sorted(refs),
                    "contracts": {
                        str(c.data["contract_ref"]): str(c.data["status"]) for c in linked
                    },
                    "tools": ["production_qc_holds", "deliveries_overdue", "contracts_status"],
                },
            )
        )
    return drafts
