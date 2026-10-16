"""Readers for the response shapes several test modules assert on."""

from __future__ import annotations


def result_ids(body: dict) -> set[str]:
    """Record ids in an assistant answer's result table."""
    return {row["id"] for row in body["result_table"]["rows"]}


def feature_refs(response) -> set[str]:
    """Record refs on the connected-data map (a GeoJSON FeatureCollection)."""
    return {f["properties"]["ref"] for f in response.json()["features"]}


def sections_by_key(response) -> dict[str, dict]:
    """A division page's sections by key; the response must be a 200."""
    assert response.status_code == 200, response.text
    return {s["key"]: s for s in response.json()["sections"]}


def section_refs(section: dict) -> list[str]:
    return [r["ref"] for r in section["rows"]]
