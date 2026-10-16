"""Unit lookups and the shape of the unit tree, shared by the routes and jobs that label things
by owning unit. The tree is /eib-group/<subsidiary>/<site>/; every module reads that shape here."""

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
    """The last path segment, upper-cased: '/eib-group/stratoc/site-4/' -> 'SITE-4'."""
    return unit_path.strip("/").split("/")[-1].upper()


GROUP_ROOT = "/eib-group/"


def _segments(unit_path: str) -> list[str]:
    return unit_path.strip("/").split("/")


def is_site(unit_path: str) -> bool:
    """A field site is a unit below a subsidiary: /eib-group/<subsidiary>/<site>/."""
    return unit_path.startswith(GROUP_ROOT) and len(_segments(unit_path)) >= 3


def subsidiary_key(unit_path: str) -> str | None:
    """'/eib-group/stratoc/site-4/' -> 'stratoc'; None for the group itself and outside units."""
    if not unit_path.startswith(GROUP_ROOT):
        return None
    segments = _segments(unit_path)
    return segments[1] if len(segments) >= 2 else None


def covers(outer: str, inner: str) -> bool:
    """`inner` is `outer` or below it. Paths end in '/', so a prefix is a whole subtree."""
    return inner.startswith(outer)


def overlaps(a: str, b: str) -> bool:
    """One unit is at or below the other (a caller and a division share some records)."""
    return covers(a, b) or covers(b, a)
