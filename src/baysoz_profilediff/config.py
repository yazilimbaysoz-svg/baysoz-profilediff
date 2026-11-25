"""Policy loading and validation for the differential gate.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

ATTRIBUTION = "Baysöz Labs <baysozlabs@proton.me>"
PRODUCT = "baysoz-profilediff"
VERSION = "1.0.0"

FRAME_KEY_MODES = ("function", "file", "line")
FAIL_ON_LEVELS = ("error", "warning", "note", "never")


class PolicyError(ValueError):
    """Raised when a policy document is invalid."""


@dataclass(frozen=True)
class Policy:
    frame_key: str = "function"
    strip_prefixes: tuple[str, ...] = ()
    frame_aliases: dict[str, str] | None = None
    max_stack_depth: int = 64
    min_delta_samples: int = 32
    z: float = 2.0
    max_total_increase_pct: float = 10.0
    max_frame_increase_pct: float = 25.0
    min_hot_share_pct: float = 2.0
    min_hot_samples: int = 16
    fail_on: str = "error"

    def validate(self) -> None:
        if self.frame_key not in FRAME_KEY_MODES:
            raise PolicyError("frame_key must be one of: " + ", ".join(FRAME_KEY_MODES))
        if self.fail_on not in FAIL_ON_LEVELS:
            raise PolicyError("fail_on must be one of: " + ", ".join(FAIL_ON_LEVELS))
        if self.max_stack_depth < 1 or self.max_stack_depth > 256:
            raise PolicyError("max_stack_depth must be between 1 and 256")
        if self.min_delta_samples < 1:
            raise PolicyError("min_delta_samples must be positive")
        if not 0.0 < self.z <= 10.0:
            raise PolicyError("z must be greater than zero and at most 10")
        if self.max_total_increase_pct < 0 or self.max_frame_increase_pct < 0:
            raise PolicyError("percentage thresholds cannot be negative")
        if not 0.0 < self.min_hot_share_pct <= 100.0:
            raise PolicyError("min_hot_share_pct must be between 0 and 100")
        if self.min_hot_samples < 1:
            raise PolicyError("min_hot_samples must be positive")
        if self.frame_aliases is not None:
            for source, target in self.frame_aliases.items():
                if not source or not target:
                    raise PolicyError("frame_aliases keys and values must be non-empty")


def default_policy() -> Policy:
    return Policy(frame_aliases={})


def policy_document(policy: Policy | None = None) -> dict[str, object]:
    selected = policy or default_policy()
    document = asdict(selected)
    document["attribution"] = ATTRIBUTION
    document["version"] = 1
    return document


def load_policy(path: Path | None) -> Policy:
    if path is None:
        policy = default_policy()
        policy.validate()
        return policy
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError("cannot read policy: " + str(exc)) from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError("policy is not valid JSON: " + str(exc)) from exc
    if not isinstance(document, dict):
        raise PolicyError("policy must be a JSON object")
    allowed = set(asdict(default_policy()).keys()) | {"attribution", "version"}
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise PolicyError("unknown policy keys: " + ", ".join(unknown))
    if document.get("attribution") != ATTRIBUTION:
        raise PolicyError("policy attribution must be: " + ATTRIBUTION)
    fields = {key: value for key, value in document.items() if key in allowed and key not in {"attribution", "version"}}
    if "frame_aliases" in fields:
        aliases = fields["frame_aliases"]
        if not isinstance(aliases, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in aliases.items()
        ):
            raise PolicyError("frame_aliases must map strings to strings")
        if aliases:
            fields["frame_aliases"] = dict(sorted(aliases.items()))
    if "strip_prefixes" in fields:
        prefixes = fields["strip_prefixes"]
        if not isinstance(prefixes, list) or not all(isinstance(item, str) for item in prefixes):
            raise PolicyError("strip_prefixes must be a list of strings")
        fields["strip_prefixes"] = tuple(sorted(prefixes))
    try:
        policy = replace(default_policy(), **fields)
    except TypeError as exc:
        raise PolicyError("policy has a field with the wrong type: " + str(exc)) from exc
    policy.validate()
    return policy
