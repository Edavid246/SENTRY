"""findings store: classified table + RLS (select/insert/update) + grants

Revision ID: c3f1a2b4d5e6
Revises: 905e0c79989b
Create Date: 2026-10-08 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3f1a2b4d5e6"
down_revision: str | None = "905e0c79989b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("analysis", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("classification_code", sa.String(length=32), nullable=False),
        sa.Column("compartments", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["classification_code"], ["classification_levels.code"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    t = "findings"
    # Same SPEC 7.1 rule as every classified table. INSERT/UPDATE use it as WITH CHECK, so
    # the runtime role cannot store a finding above its clearance, outside its unit or
    # compartments. No DELETE is granted.
    rule = (
        "NULLIF(current_setting('app.data_scope', true),'')='standard'"
        " AND NULLIF(current_setting('app.clearance_rank',true),'')::int >= "
        f"(SELECT cl.rank FROM classification_levels cl WHERE cl.code={t}.classification_code)"
        f" AND {t}.compartments::text[] <@ (NULLIF(current_setting("
        "'app.compartments',true),'')::text[])"
        " AND EXISTS (SELECT 1 FROM units u WHERE u.id="
        f"{t}.unit_id AND starts_with(u.path,NULLIF(current_setting('app.unit_path',true),'')))"
    )
    op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {t}_select ON {t} FOR SELECT TO gateway_app USING ({rule})")
    op.execute(f"CREATE POLICY {t}_insert ON {t} FOR INSERT TO gateway_app WITH CHECK ({rule})")
    op.execute(
        f"CREATE POLICY {t}_update ON {t} FOR UPDATE TO gateway_app"
        f" USING ({rule}) WITH CHECK ({rule})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {t} TO gateway_app")


def downgrade() -> None:
    op.drop_table("findings")
