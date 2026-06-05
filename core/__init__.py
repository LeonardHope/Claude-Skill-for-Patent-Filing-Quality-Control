"""core — the shared QC engine surface for all frontends (v2).

Phase 1 introduces the engine↔frontend contract (the Result + Evidence schema)
and an adapter from the existing engine to it, WITHOUT changing any check
behavior. Later phases move the checks themselves into core/checks/ and have
them emit structured evidence. See ../DESIGN.md.
"""
from .result import (  # noqa: F401
    Result, DocumentRef, PageMeta, Issue, Evidence, Locator,
)
