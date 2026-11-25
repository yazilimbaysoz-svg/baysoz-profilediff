"""Differential gate tests covering regressions, noise, and quality rules.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from baysoz_profilediff.analyze import compare, should_fail
from baysoz_profilediff.config import Policy, default_policy
from baysoz_profilediff.normalize import aggregate
from baysoz_profilediff.proto import decode_profile
from tests.fixtures import ProfileBuilder

HOT = (("svc.hot", "/srv/app/hot.go", 10), ("svc.main", "/srv/app/main.go", 1))
COLD = (("svc.cold", "/srv/app/cold.go", 20), ("svc.main", "/srv/app/main.go", 1))
NEW = (("svc.new", "/srv/app/new.go", 30), ("svc.main", "/srv/app/main.go", 1))


def _view(builder: ProfileBuilder) -> object:
    return aggregate(decode_profile(builder.build()), default_policy())


def _profile(count_hot: int, count_cold: int = 0, count_new: int = 0) -> ProfileBuilder:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    for _ in range(count_hot):
        builder.add_samples(HOT, (1,))
    for _ in range(count_cold):
        builder.add_samples(COLD, (1,))
    for _ in range(count_new):
        builder.add_samples(NEW, (1,))
    return builder


def test_identical_profiles_are_clean() -> None:
    analysis = compare(_view(_profile(120)), _view(_profile(120)), default_policy())
    assert analysis.findings == ()
    assert analysis.comparable_types == ("cpu/nanoseconds",)
    assert not should_fail(analysis, "error")


def test_small_sampling_noise_is_ignored() -> None:
    analysis = compare(_view(_profile(100)), _view(_profile(104)), default_policy())
    assert all(item.rule not in {"PROF001", "PROF002", "PROF004"} for item in analysis.findings)


def test_hot_path_regression_is_detected_with_stable_ids() -> None:
    baseline = _view(_profile(100, 100))
    candidate = _view(_profile(100, 900))
    first = compare(baseline, candidate, default_policy())
    second = compare(baseline, candidate, default_policy())
    rules = {item.rule for item in first.findings}
    assert {"PROF001", "PROF002", "PROF003"} <= rules
    assert first.as_dict() == second.as_dict()
    assert all(len(item.finding_id) == 16 for item in first.findings)
    assert should_fail(first, "error")


def test_new_hot_frame_is_reported() -> None:
    analysis = compare(_view(_profile(200)), _view(_profile(200, 0, 200)), default_policy())
    assert any(item.rule == "PROF004" and item.frame == "svc.new" for item in analysis.findings)


def test_resolved_hot_frame_is_a_note() -> None:
    analysis = compare(_view(_profile(200, 100)), _view(_profile(200)), default_policy())
    resolved = [item for item in analysis.findings if item.rule == "PROF005"]
    assert resolved and all(item.severity == "note" for item in resolved)


def test_negative_values_are_rejected() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    builder.add_samples(HOT, (-1,))
    analysis = compare(_view(_profile(10)), _view(builder), default_policy())
    assert any(item.rule == "PROF006" and item.severity == "error" for item in analysis.findings)


def test_mismatched_sample_types_are_reported() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("wallclock/nanoseconds", "nanoseconds")
    builder.add_samples(HOT, (10,))
    analysis = compare(_view(_profile(10)), _view(builder), default_policy())
    assert analysis.comparable_types == ()
    assert any(item.rule == "PROF006" and item.severity == "error" for item in analysis.findings)


def test_policy_thresholds_can_suppress_and_tighten() -> None:
    baseline = _view(_profile(100, 100))
    candidate = _view(_profile(100, 900))
    tolerant = compare(baseline, candidate, Policy(max_total_increase_pct=1000, max_frame_increase_pct=1000))
    assert not any(item.rule in {"PROF001", "PROF002", "PROF003"} for item in tolerant.findings)
    strict = compare(baseline, candidate, Policy(min_delta_samples=1, z=0.1))
    assert should_fail(strict, "error")


def test_fail_on_levels() -> None:
    policy = Policy(min_hot_share_pct=1.0)
    baseline = aggregate(decode_profile(_profile(1000, 16).build()), policy)
    candidate = aggregate(decode_profile(_profile(1000).build()), policy)
    analysis = compare(baseline, candidate, policy)
    assert any(item.rule == "PROF005" for item in analysis.findings)
    assert not should_fail(analysis, "error")
    assert should_fail(analysis, "note")
    assert not should_fail(analysis, "never")
