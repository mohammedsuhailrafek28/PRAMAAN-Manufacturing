"""Deterministic recall-decision engine (Phase 1). Pure functions, stdlib only.

The engine never reads the supplied expected-outcome file; only tests/ and harness/ do.
"""
from .engine import Config, evaluate
from .lifecycle import evaluate_series
from .loader import (full_watermark, load_case, load_policies, watermark_at)

__all__ = ["Config", "evaluate", "evaluate_series", "load_case",
           "load_policies", "full_watermark", "watermark_at"]
