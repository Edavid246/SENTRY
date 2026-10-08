"""conversations: UPDATE of the label and updated_at only (RLS update policy + column grant)

A conversation holds every turn stored in it, so its label must rise with each
turn (highest classification, union of compartments) and updated_at must move.
The runtime role may update only those three columns, and only on a
conversation it can see, to a label it holds (USING and WITH CHECK are the same
SPEC 7.1 rule as SELECT/INSERT).

Revision ID: e8b3d1f0a7c2
Revises: c3f1a2b4d5e6
Create Date: 2026-10-08 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e8b3d1f0a7c2"
down_revision: str | None = "c3f1a2b4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    t = "conversations"
    rule = (
        "NULLIF(current_setting('app.data_scope', true),'')='standard'"
        " AND NULLIF(current_setting('app.clearance_rank',true),'')::int >= "
        f"(SELECT cl.rank FROM classification_levels cl WHERE cl.code={t}.classification_code)"
        f" AND {t}.compartments::text[] <@ (NULLIF(current_setting("
        "'app.compartments',true),'')::text[])"
        " AND EXISTS (SELECT 1 FROM units u WHERE u.id="
        f"{t}.unit_id AND starts_with(u.path,NULLIF(current_setting('app.unit_path',true),'')))"
    )
    op.execute(
        f"CREATE POLICY {t}_update ON {t} FOR UPDATE TO gateway_app"
        f" USING ({rule}) WITH CHECK ({rule})"
    )
    op.execute(
        f"GRANT UPDATE (classification_code, compartments, updated_at) ON {t} TO gateway_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE UPDATE (classification_code, compartments, updated_at)"
        " ON conversations FROM gateway_app"
    )
    op.execute("DROP POLICY IF EXISTS conversations_update ON conversations")
