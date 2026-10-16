"""Shared test helpers. Test modules import from here, never from each other.

`tests/` is on the pytest `pythonpath` (pyproject.toml), so these import as `support.<module>`:

* `http`: log in, auth header, GET as a user, ask the assistant;
* `audit`: read the trail as the auditor, newest matching event, the chain tip;
* `contexts`: the hand-written SPEC 7.4 user contexts and the token-resolved `ctx_for`;
* `fakes`: model fakes for the model seam;
* `responses`: small readers for response shapes (result-table ids, map refs, sections);
* `scoped`: run data-access code on an authorized Scope outside a route.

The gold visibility oracle stays in `tests/authz/expected.py` (`authz.expected`).
"""
