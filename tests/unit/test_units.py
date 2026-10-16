"""The unit-tree vocabulary in app.units, and the home grouping rule built on it."""

import pytest
from app.divisions.catalog import FIELD_OPS, division_key
from app.units import covers, is_site, overlaps, subsidiary_key, unit_slug

GROUP = "/eib-group/"
STRATOC = "/eib-group/stratoc/"
SITE = "/eib-group/stratoc/site-4/"
OUTSIDE = "/partner/team/"


@pytest.mark.parametrize(
    ("path", "site", "subsidiary"),
    [
        (GROUP, False, None),
        (STRATOC, False, "stratoc"),
        (SITE, True, "stratoc"),
        ("/eib-group/stratoc/site-4/cell-1/", True, "stratoc"),
        (OUTSIDE, False, None),
        ("/eib-groupx/stratoc/site-4/", False, None),  # a prefix of the name is not the group
    ],
)
def test_shape_of_a_path(path: str, site: bool, subsidiary: str | None) -> None:
    assert is_site(path) is site
    assert subsidiary_key(path) == subsidiary


def test_covers_is_the_unit_or_below_it() -> None:
    assert covers(GROUP, SITE) and covers(STRATOC, SITE) and covers(SITE, SITE)
    assert not covers(SITE, STRATOC)
    assert not covers("/eib-group/giga/", SITE)


def test_overlaps_either_way() -> None:
    assert overlaps(SITE, GROUP) and overlaps(GROUP, SITE)
    assert not overlaps(SITE, "/eib-group/giga/")


def test_unit_slug() -> None:
    assert unit_slug(SITE) == "SITE-4"


@pytest.mark.parametrize(
    ("path", "record", "finding"),
    [
        (GROUP, None, None),  # group-level: no division
        (OUTSIDE, None, None),
        (STRATOC, "stratoc", "stratoc"),
        (SITE, FIELD_OPS, "stratoc"),  # a finding about a site stays with its subsidiary
    ],
)
def test_home_groups_records_and_findings_by_division(
    path: str, record: str | None, finding: str | None
) -> None:
    assert division_key(path) == record
    assert division_key(path, finding=True) == finding
