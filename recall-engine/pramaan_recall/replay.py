"""Reproduce a stored decision under the semantics it was made with.

New evaluations use Config.default(); a stored decision names its own profile
(`semanticsProfile`). Records written before profiles existed have none and are legacy.
"""
import hashlib
import json

from .engine import LEGACY, Config, evaluate


def replay(case, policy, coverage, record):
    """Re-run `record` (a stored decision) against the same inputs. Never uses the default
    profile. Refuses if the coverage policy differs from the one the decision was made with."""
    profile = record.get("semanticsProfile", LEGACY)
    digest = record.get("coverageDigest")
    if digest and digest != hashlib.sha256(json.dumps(coverage, sort_keys=True).encode()).hexdigest():
        raise ValueError("coverage policy differs from the one the decision was made with")
    return evaluate(case, policy, coverage, record["watermark"], Config.from_profile(profile))
