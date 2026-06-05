"""report — the static HTML report frontend, a consumer of core's Result.

Mirrors the app frontend: both render the same Result contract, so the engine's
output has a single shape and the report and the interactive viewer never drift.
This is the v2 report; the shipping skill's report still lives in the monolith
(scripts/qc_patent_filing.py) on main.
"""
from .html import render  # noqa: F401
