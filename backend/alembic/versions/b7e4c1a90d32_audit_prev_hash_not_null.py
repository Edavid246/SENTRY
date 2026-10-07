"""audit_events prev_hash not null, sequence UPDATE for the chain writer

Every row now belongs to a chain written by the audit slice (step 7), so
prev_hash is mandatory from here on. Both databases hold zero audit rows at
upgrade time, so the tightening needs no backfill.

The chain writer assigns explicit seqs under the advisory lock and must then
re-sync the serial sequence (setval needs UPDATE). Sequence privileges do not
weaken the append-only posture of the table itself: audit_events still grants
INSERT and SELECT only.

Revision ID: b7e4c1a90d32
Revises: d6fad2764629
Create Date: 2026-10-07 09:12:44.815603
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1a90d32"
down_revision: str | None = "d6fad2764629"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_events", "prev_hash", existing_type=sa.String(length=64), nullable=False)
    op.execute("GRANT UPDATE ON SEQUENCE audit_events_seq_seq TO gateway_app")


def downgrade() -> None:
    op.execute("REVOKE UPDATE ON SEQUENCE audit_events_seq_seq FROM gateway_app")
    op.alter_column("audit_events", "prev_hash", existing_type=sa.String(length=64), nullable=True)
