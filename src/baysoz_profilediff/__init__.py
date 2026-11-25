"""Baysöz Labs pprof differential regression gate.

Baysöz Labs <baysozlabs@proton.me>
"""

from .analyze import Analysis, Finding, compare, should_fail
from .config import ATTRIBUTION, VERSION, Policy, default_policy, load_policy, policy_document
from .normalize import aggregate
from .proto import ProfileData, ProfileFormatError, decode_profile
from .report import render_json, render_sarif, render_text

__all__ = [
    "ATTRIBUTION",
    "VERSION",
    "Analysis",
    "Finding",
    "Policy",
    "ProfileData",
    "ProfileFormatError",
    "aggregate",
    "compare",
    "decode_profile",
    "default_policy",
    "load_policy",
    "policy_document",
    "render_json",
    "render_sarif",
    "render_text",
    "should_fail",
]
