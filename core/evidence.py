"""Post-hoc evidence bridge for checks still living in the monolith.

Every check that currently emits evidence has been migrated to core/checks/ and
emits it natively, so there is nothing to enrich right now. This stub is kept as
the seam for the case where a not-yet-migrated check needs a receipt before its
full migration — add a per-id block here, exactly as before.
"""
from pathlib import Path
from typing import Dict

from .result import Result


def enrich(result: Result, doc_paths: Dict[str, Path]) -> Result:
    """Attach evidence to issues for checks not yet migrated to core/checks/.
    Currently a no-op (all evidence-bearing checks are native). Never raises."""
    return result
