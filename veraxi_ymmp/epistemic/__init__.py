"""veraxi_ymmp.epistemic subpackage."""
from __future__ import annotations

from veraxi_ymmp.epistemic.temporal_gate import (
    StaleTemporalSourceError,
    TemporalViolation,
    audit_temporal_recency,
    enforce_temporal_recency,
)

__all__ = [
    "StaleTemporalSourceError",
    "TemporalViolation",
    "audit_temporal_recency",
    "enforce_temporal_recency",
]
