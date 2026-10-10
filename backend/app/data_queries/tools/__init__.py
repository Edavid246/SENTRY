"""Typed, parameterized query tools (SPEC 8.2 data pathway).

Each tool validates its parameters, then asks the adapter for records on the caller's authorized
Scope; it never builds SQL and never touches the record tables. See `base` for what every tool
shares (`@tool`, `Table`, the validators). Importing a domain module registers its tools in
`TOOLS`, which `registry` executes.

  compliance   equipment, certifications, stock, training, personnel
  uas          missions, fleet, sensors, detections
  commercial   contracts, deliveries
  production   production runs, serial traceability
  forensics    cases, evidence, custody
  findings     correlation findings (our own store, no unit path)
"""

from app.data_queries.tools import (
    commercial,
    compliance,
    findings,
    forensics,
    production,
    uas,
)
from app.data_queries.tools.base import TOOLS, ToolFn, ToolResult
from app.data_queries.tools.compliance import expired_certifications

__all__ = [
    "TOOLS",
    "ToolFn",
    "ToolResult",
    "commercial",
    "compliance",
    "expired_certifications",
    "findings",
    "forensics",
    "production",
    "uas",
]
