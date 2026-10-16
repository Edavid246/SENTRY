"""The group's divisions: which they are, what their dashboards show, what needs attention.

  * `catalog`: the five divisions and which division a record counts toward,
  * `specs`: one `SectionSpec` per dashboard section (presentation only),
  * `view`: runs a division's specs as audited typed tools for the caller,
  * `attention`: the home cards' counts of what needs attention.

Domain logic only: the routes in `app.api` (home, divisions, reports) hold the HTTP side.
"""
