# Decisions log

Dated one-line entries for places where the build deliberately departs from a
default in docs/SPEC.md. Invariants (see AGENTS.md) never appear here: changing one
needs a conversation first.

Format: `YYYY-MM-DD — what changed — why`

- 2026-10-09 — AGENTS.md split into invariants vs defaults; spec binds only on invariants — spec is a v0.1 draft and "stop and ask" on every difference was blocking work.
- 2026-10-09 — Pivot Task 1: units renamed to the client's group (EIB Group, Briech UAS, EIB Stratoc, Stratoc Site Team 4, Giga Forensics, Poctova, Group IT, Group Audit); users renamed by role (`owner`, `coo`, ...); classification keys unchanged, display names Open/Internal/Confidential/Government-sensitive; compartments CLIENT-A..D added (generic agency labels) — demo is for one private group owner, not an army HQ; role strings kept because authz/policy.py and the shell depend on them.
