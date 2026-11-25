"""Report renderer tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json

from baysoz_profilediff.analyze import compare
from baysoz_profilediff.config import ATTRIBUTION, VERSION, default_policy
from baysoz_profilediff.normalize import aggregate
from baysoz_profilediff.proto import decode_profile
from baysoz_profilediff.report import render_inspect, render_json, render_sarif, render_text
from tests.fixtures import ProfileBuilder

HOT = (("svc.hot", "/srv/app/hot.go", 10), ("svc.main", "/srv/app/main.go", 1))
COLD = (("svc.cold", "/srv/app/cold.go", 20), ("svc.main", "/srv/app/main.go", 1))


def _builder(count_hot: int, count_cold: int) -> ProfileBuilder:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    for _ in range(count_hot):
        builder.add_samples(HOT, (1,))
    for _ in range(count_cold):
        builder.add_samples(COLD, (1,))
    return builder


def test_reports_are_valid_and_attributed() -> None:
    analysis = compare(
        aggregate(decode_profile(_builder(100, 100).build()), default_policy()),
        aggregate(decode_profile(_builder(100, 900).build()), default_policy()),
        default_policy(),
    )
    sarif = json.loads(render_sarif(analysis))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["version"] == VERSION
    assert sarif["runs"][0]["properties"]["attribution"] == ATTRIBUTION
    assert sarif["runs"][0]["results"]
    assert all(
        result["properties"]["attribution"] == ATTRIBUTION
        for result in sarif["runs"][0]["results"]
    )
    assert {result["level"] for result in sarif["runs"][0]["results"]} <= {"error", "warning", "note"}
    document = json.loads(render_json(analysis))
    assert document["attribution"] == ATTRIBUTION
    assert document["tool"] == "baysoz-profilediff"
    assert ATTRIBUTION in render_text(analysis)
    assert render_text(analysis) == render_text(analysis)


def test_clean_report_has_pass_marker() -> None:
    analysis = compare(
        aggregate(decode_profile(_builder(100, 0).build()), default_policy()),
        aggregate(decode_profile(_builder(100, 0).build()), default_policy()),
        default_policy(),
    )
    assert "PASS" in render_text(analysis)
    assert json.loads(render_sarif(analysis))["runs"][0]["results"] == []


def test_inspect_report_is_attributed() -> None:
    profile = decode_profile(_builder(3, 2).build())
    assert ATTRIBUTION in render_inspect(profile, "sample.pb.gz")
    assert "samples: 5" in render_inspect(profile, "sample.pb.gz")
