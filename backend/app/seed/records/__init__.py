"""Every demo record, in the order they are seeded (the order sets each record's retrieved_at)."""

from __future__ import annotations

from app.seed.records import assets, base, connected, contracts, data_pathway, forensics, production

RECORDS = [
    *base.RECORDS,
    *data_pathway.RECORDS,
    *connected.RECORDS,
    *contracts.RECORDS,
    *production.RECORDS,
    *assets.RECORDS,
    *forensics.RECORDS,
]
