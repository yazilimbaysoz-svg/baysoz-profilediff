"""Deterministic human, JSON, and SARIF report emitters.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
from typing import Any

from .analyze import Analysis, RULE_DESCRIPTIONS
from .config import ATTRIBUTION, PRODUCT, VERSION

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _rule_descriptors() -> list[dict[str, str]]:
    return [
        {
            "id": rule,
            "name": description.replace(" ", "_").replace("-", "_"),
            "shortDescription": {"text": description},
        }
        for rule, description in sorted(RULE_DESCRIPTIONS.items())
    ]


def render_sarif(analysis: Analysis) -> str:
    results: list[dict[str, Any]] = []
    for finding in analysis.findings:
        results.append(
            {
                "ruleId": finding.rule,
                "level": finding.severity,
                "message": {"text": finding.message},
                "locations": [
                    {
                        "logicalLocations": [
                            {
                                "name": finding.frame,
                                "kind": "function",
                            }
                        ]
                    }
                ],
                "partialFingerprints": {"stableId": finding.finding_id},
                "properties": {
                    "sampleType": finding.sample_type,
                    "observed": round(finding.observed, 4),
                    "expected": round(finding.expected, 4),
                    "threshold": round(finding.threshold, 4),
                    "attribution": ATTRIBUTION,
                },
            }
        )
    document = {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": PRODUCT,
                        "fullName": PRODUCT + " by " + ATTRIBUTION,
                        "version": VERSION,
                        "informationUri": "https://github.com/yazilimbaysoz-svg/baysoz-profilediff",
                        "rules": _rule_descriptors(),
                    }
                },
                "results": results,
                "properties": {
                    "attribution": ATTRIBUTION,
                    "comparableSampleTypes": list(analysis.comparable_types),
                    "counts": analysis.by_severity,
                },
            }
        ],
    }
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render_json(analysis: Analysis) -> str:
    return json.dumps(analysis.as_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render_text(analysis: Analysis) -> str:
    lines = [
        PRODUCT + " " + VERSION + " differential report",
        "Baysöz Labs <baysozlabs@proton.me>",
        "comparable sample types: " + (", ".join(analysis.comparable_types) or "none"),
        "findings: "
        + str(analysis.by_severity["error"])
        + " error / "
        + str(analysis.by_severity["warning"])
        + " warning / "
        + str(analysis.by_severity["note"])
        + " note",
    ]
    if not analysis.findings:
        lines.append("PASS: no regressions detected")
        return "\n".join(lines) + "\n"
    lines.append("")
    lines.append("ID               SEVERITY  RULE     FRAME / SAMPLE TYPE")
    lines.append("-" * 78)
    for finding in analysis.findings:
        lines.append(
            finding.finding_id
            + "  "
            + finding.severity.upper().ljust(8)
            + "  "
            + finding.rule
            + "  "
            + finding.frame[:38]
            + " | "
            + finding.sample_type[:20]
        )
        lines.append("    " + finding.message)
    return "\n".join(lines) + "\n"


def render_inspect(profile: Any, path: str) -> str:
    lines = [
        PRODUCT + " " + VERSION + " profile inspection",
        "Baysöz Labs <baysozlabs@proton.me>",
        "path: " + path,
        "samples: " + str(profile.sample_count),
        "duration_ns: " + str(profile.duration_ns),
        "default sample type: " + profile.default_sample_type,
        "sample types:",
    ]
    for item in profile.sample_types:
        lines.append("  - " + item.name + " [" + item.unit + "]")
    lines.append("mappings: " + str(profile.mapping_count))
    return "\n".join(lines) + "\n"
