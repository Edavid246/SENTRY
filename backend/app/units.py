"""Unit lookups shared by the routes and jobs that label things by owning unit."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def unit_names(conn: Connection) -> dict[str, str]:
    """Readable unit name by unit path (unit names are not classified)."""
    return {
        str(row.path): str(row.name)
        for row in conn.execute(text("SELECT path, name FROM units")).all()
    }


def unit_slug(unit_path: str) -> str:
    """The last path segment, upper-cased: '/command-a/bde-2/bn-4/' -> 'BN-4'."""
    return unit_path.strip("/").split("/")[-1].upper()
