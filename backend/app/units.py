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


def depth(unit_path: str) -> int:
    return len(unit_path.strip("/").split("/"))


def is_subsidiary(unit_path: str) -> bool:
    return unit_path.startswith(GROUP_ROOT) and depth(unit_path) == 2


def is_site(unit_path: str) -> bool:
    """A field site is a unit below a subsidiary: /eib-group/<subsidiary>/<site>/."""
    return unit_path.startswith(GROUP_ROOT) and depth(unit_path) >= 3


def subsidiary_path(unit_path: str) -> str:
    """'/eib-group/stratoc/site-4/' -> '/eib-group/stratoc/'; other units stand for themselves."""
    if unit_path.startswith(GROUP_ROOT) and depth(unit_path) >= 2:
        return f"{GROUP_ROOT}{unit_path.strip('/').split('/')[1]}/"
    return unit_path
