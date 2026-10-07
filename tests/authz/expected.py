"""Gold visibility sets for the demo corpus — the independent oracle.

Hand-authored from the confirmed corpus table and the literal SPEC 7.1
rule (standard scope AND clearance >= row rank AND row compartments subset
of user compartments AND row unit at or below the user's unit, strictly
downward). Deliberately NOT derived from app.seed: a seeding bug must not
be able to rewrite its own expectations.

Verified sets (16 documents, 27 records in the corpus):

    a.bello    14 documents, 26 records
    a.okafor    6 documents, 18 records
    t.adeyemi   1 document,  9 records
    k.musa      1 document,  1 record
    s.eze       none  (data_scope=none)
    f.danjuma   none  (data_scope=audit)

Q2 keyword expectation: exactly one chunk containing KEYWORD in each of
DOC-001, DOC-006 and DOC-013 (nowhere else); per-user counts follow from
the gold document sets.
"""

KEYWORD = "maintenance"

GOLD_DOCUMENTS: dict[str, frozenset[str]] = {
    "a.bello": frozenset(
        {
            "DOC-001",
            "DOC-002",
            "DOC-003",
            "DOC-004",
            "DOC-005",
            "DOC-006",
            "DOC-007",
            "DOC-008",
            "DOC-009",
            "DOC-010",
            "DOC-013",
            "DOC-014",
            "DOC-015",
            "DOC-016",
        }
    ),
    "a.okafor": frozenset({"DOC-001", "DOC-002", "DOC-003", "DOC-009", "DOC-013", "DOC-016"}),
    "t.adeyemi": frozenset({"DOC-003"}),
    "k.musa": frozenset({"DOC-006"}),
    "s.eze": frozenset(),
    "f.danjuma": frozenset(),
}

GOLD_RECORDS: dict[str, frozenset[str]] = {
    "a.bello": frozenset(
        {
            "REC-001",
            "REC-002",
            "REC-003",
            "REC-004",
            "REC-005",
            "REC-006",
            "REC-007",
            "REC-009",
            "REC-010",
            *(f"REC-0{n}" for n in range(11, 28)),
        }
    ),
    "a.okafor": frozenset(
        {"REC-001", "REC-002", "REC-003", "REC-005", "REC-010"}
        | {"REC-011", "REC-012", "REC-013", "REC-014", "REC-015", "REC-017"}
        | {"REC-019", "REC-020", "REC-021", "REC-022", "REC-025", "REC-026", "REC-027"}
    ),
    "t.adeyemi": frozenset(
        {"REC-002", "REC-011", "REC-012", "REC-017", "REC-019", "REC-020", "REC-025"}
        | {"REC-026", "REC-027"}
    ),
    "k.musa": frozenset({"REC-009"}),
    "s.eze": frozenset(),
    "f.danjuma": frozenset(),
}

GOLD_KEYWORD_CHUNK_COUNTS: dict[str, int] = {
    "a.bello": 3,
    "a.okafor": 2,
    "t.adeyemi": 0,
    "k.musa": 1,
    "s.eze": 0,
    "f.danjuma": 0,
}
