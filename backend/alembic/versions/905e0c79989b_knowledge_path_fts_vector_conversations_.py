"""knowledge path: FTS vector + conversations/messages + grants + RLS

Revision ID: 905e0c79989b
Revises: b7e4c1a90d32
Create Date: 2026-10-07 15:05:52.446326
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "905e0c79989b"
down_revision: str | None = "b7e4c1a90d32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.execute("UPDATE chunks SET search_vector = to_tsvector('english', coalesce(text,''))")
    # Keep search_vector correct for every insert/update (seed, ingestion worker
    # and any future writer) without relying on the caller to set it.
    op.execute(
        """
        CREATE FUNCTION chunks_search_vector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', coalesce(NEW.text, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_chunks_search_vector"
        " BEFORE INSERT OR UPDATE OF text ON chunks"
        " FOR EACH ROW EXECUTE FUNCTION chunks_search_vector_trigger()"
    )
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING GIN (search_vector)")
    op.alter_column("chunks", "search_vector", nullable=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("classification_code", sa.String(length=32), nullable=False),
        sa.Column("compartments", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("classification_code", sa.String(length=32), nullable=False),
        sa.Column("compartments", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["classification_code"], ["classification_levels.code"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # SELECT uses the same rule as the other classified tables; INSERT (turns
    # are append-only) uses it as a WITH CHECK so a user cannot store a turn
    # marked above their clearance, outside their unit or compartments.
    for t in ("conversations", "messages"):
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
    op.execute("GRANT SELECT, INSERT ON conversations, messages TO gateway_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_search_vector ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_search_vector_trigger()")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_column("chunks", "search_vector")
