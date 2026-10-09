"""Gold visibility sets for the demo corpus — the independent oracle.

Hand-authored from the confirmed corpus table and the literal SPEC 7.1
rule (standard scope AND clearance >= row rank AND row compartments subset
of user compartments AND row unit at or below the user's unit, strictly
downward). Deliberately NOT derived from app.seed: a seeding bug must not
be able to rewrite its own expectations.

Verified sets (16 documents, 62 records in the corpus):

    owner    14 documents, 61 records
    logistics.head    6 documents, 42 records
    coo   1 document,  24 records
    briech.lead      1 document,  8 records
    group.it       none  (data_scope=none)
    group.audit   none  (data_scope=audit)

Q2 keyword expectation: exactly one chunk containing KEYWORD in each of
DOC-001, DOC-006 and DOC-013 (nowhere else); per-user counts follow from
the gold document sets.
"""

KEYWORD = "maintenance"

GOLD_DOCUMENTS: dict[str, frozenset[str]] = {
    "owner": frozenset(
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
    "logistics.head": frozenset({"DOC-001", "DOC-002", "DOC-003", "DOC-009", "DOC-013", "DOC-016"}),
    "coo": frozenset({"DOC-003"}),
    "briech.lead": frozenset({"DOC-006"}),
    "group.it": frozenset(),
    "group.audit": frozenset(),
}

GOLD_RECORDS: dict[str, frozenset[str]] = {
    "owner": frozenset(
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
            *(f"REC-0{n}" for n in range(11, 63)),
        }
    ),
    "logistics.head": frozenset(
        {"REC-001", "REC-002", "REC-003", "REC-005", "REC-010"}
        | {"REC-011", "REC-012", "REC-013", "REC-014", "REC-015", "REC-017"}
        | {"REC-019", "REC-020", "REC-021", "REC-022", "REC-025", "REC-026", "REC-027"}
        # planted-pattern: Site 4 faults 028-035 (036 is Secret), Stratoc faults, maintainers
        | {f"REC-0{n}" for n in range(28, 36)}
        | {"REC-037", "REC-038", "REC-039", "REC-040", "REC-041", "REC-042"}
        | {"REC-043", "REC-045"}  # training events in Stratoc / Site 4 (044 is the Briech UAS)
        # connected tech: depot sensors + detections (053 is UAS-OPS, 055-060 Briech UAS missions)
        | {"REC-046", "REC-047", "REC-048", "REC-049", "REC-050", "REC-051", "REC-052", "REC-054"}
    ),
    "coo": frozenset(
        {"REC-002", "REC-011", "REC-012", "REC-017", "REC-019", "REC-020", "REC-025"}
        | {"REC-026", "REC-027"}
        | {f"REC-0{n}" for n in range(28, 36)}  # Site 4 faults, not the Secret 036
        | {"REC-041", "REC-042"}
        | {"REC-045"}
        # Site 4 sensor and Restricted detections (054 is Confidential)
        | {"REC-046", "REC-048", "REC-049", "REC-050"}
    ),
    "briech.lead": frozenset(
        {"REC-009", "REC-044"}
        # UAS-OPS detection and Confidential missions (060 is Secret)
        | {"REC-053", "REC-055", "REC-056", "REC-057", "REC-058", "REC-059"}
    ),
    "group.it": frozenset(),
    "group.audit": frozenset(),
}

GOLD_KEYWORD_CHUNK_COUNTS: dict[str, int] = {
    "owner": 3,
    "logistics.head": 2,
    "coo": 0,
    "briech.lead": 1,
    "group.it": 0,
    "group.audit": 0,
}
