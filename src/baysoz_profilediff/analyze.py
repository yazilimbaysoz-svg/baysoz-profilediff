"""Noise-aware differential analysis of two aggregated pprof profiles.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .config import ATTRIBUTION, Policy
from .normalize import AggregatedProfile

SEVERITIES = ("error", "warning", "note")
RULE_DESCRIPTIONS = {
    "PROF001": "aggregate sample-rate regression",
    "PROF002": "frame self-cost share regression",
    "PROF003": "hot-path cumulative share regression",
    "PROF004": "new hot frame",
    "PROF005": "resolved hot frame",
    "PROF006": "profile quality advisory",
}


@dataclass(frozen=True)
class Finding:
    finding_id: str
    rule: str
    severity: str
    message: str
    sample_type: str
    frame: str
    observed: float
    expected: float
    threshold: float

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.finding_id,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "sample_type": self.sample_type,
            "frame": self.frame,
            "observed": round(self.observed, 4),
            "expected": round(self.expected, 4),
            "threshold": round(self.threshold, 4),
            "attribution": ATTRIBUTION,
        }


@dataclass(frozen=True)
class Analysis:
    findings: tuple[Finding, ...]
    comparable_types: tuple[str, ...]
    baseline_rate: tuple[float, ...]
    candidate_rate: tuple[float, ...]

    @property
    def by_severity(self) -> dict[str, int]:
        return {
            level: sum(1 for item in self.findings if item.severity == level)
            for level in SEVERITIES
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "tool": "baysoz-profilediff",
            "version": "1.0.0",
            "attribution": ATTRIBUTION,
            "comparable_sample_types": list(self.comparable_types),
            "counts": self.by_severity,
            "findings": [item.as_dict() for item in self.findings],
        }


def _stable_id(rule: str, sample_type: str, frame: str) -> str:
    material = "|".join((rule, sample_type, frame)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _finding(
    rule: str,
    severity: str,
    message: str,
    sample_type: str,
    frame: str,
    observed: float,
    expected: float,
    threshold: float,
) -> Finding:
    return Finding(
        finding_id=_stable_id(rule, sample_type, frame),
        rule=rule,
        severity=severity,
        message=message,
        sample_type=sample_type,
        frame=frame,
        observed=observed,
        expected=expected,
        threshold=threshold,
    )


def _noise_threshold(expected: float, observed: float, policy: Policy) -> float:
    sigma = math.sqrt(max(expected, 0.0) + max(observed, 0.0) + 1.0)
    return max(float(policy.min_delta_samples), policy.z * sigma)


def _rate(total: int, duration_ns: int) -> float:
    if duration_ns > 0:
        return total * 1_000_000_000 / duration_ns
    return float(total)


def _quality_findings(
    baseline: AggregatedProfile,
    candidate: AggregatedProfile,
    sample_type: str,
) -> list[Finding]:
    findings: list[Finding] = []
    if candidate.negative_values:
        findings.append(
            _finding(
                "PROF006",
                "error",
                "candidate contains negative sample values; refusing to diff a diff profile",
                sample_type,
                "<profile>",
                float(candidate.negative_values),
                0.0,
                0.0,
            )
        )
    if candidate.sample_count == 0:
        findings.append(
            _finding(
                "PROF006",
                "error",
                "candidate profile has no samples",
                sample_type,
                "<profile>",
                0.0,
                0.0,
                0.0,
            )
        )
    if baseline.sample_count == 0:
        findings.append(
            _finding(
                "PROF006",
                "warning",
                "baseline profile has no samples; deltas are advisory only",
                sample_type,
                "<profile>",
                0.0,
                0.0,
                0.0,
            )
        )
    if baseline.duration_ns <= 0 or candidate.duration_ns <= 0:
        findings.append(
            _finding(
                "PROF006",
                "warning",
                "missing capture duration; counts are compared as rates per profile",
                sample_type,
                "<profile>",
                float(baseline.duration_ns),
                float(candidate.duration_ns),
                0.0,
            )
        )
    if candidate.empty_stacks:
        findings.append(
            _finding(
                "PROF006",
                "warning",
                "candidate contains samples without a resolvable stack",
                sample_type,
                "<profile>",
                float(candidate.empty_stacks),
                0.0,
                0.0,
            )
        )
    if candidate.truncated_stacks:
        findings.append(
            _finding(
                "PROF006",
                "note",
                "candidate contains stacks truncated by policy.max_stack_depth",
                sample_type,
                "<profile>",
                float(candidate.truncated_stacks),
                0.0,
                0.0,
            )
        )
    if candidate.unknown_frames:
        findings.append(
            _finding(
                "PROF006",
                "note",
                "candidate contains frames without symbol names",
                sample_type,
                "<profile>",
                float(candidate.unknown_frames),
                0.0,
                0.0,
            )
        )
    return findings


def compare(baseline: AggregatedProfile, candidate: AggregatedProfile, policy: Policy) -> Analysis:
    findings: list[Finding] = []
    baseline_names = [name for name, _unit in baseline.sample_types]
    candidate_names = [name for name, _unit in candidate.sample_types]
    missing = sorted(set(baseline_names) - set(candidate_names))
    added = sorted(set(candidate_names) - set(baseline_names))
    if missing or added:
        detail = "missing=" + ",".join(missing) + "; added=" + ",".join(added)
        findings.append(
            _finding(
                "PROF006",
                "error" if not set(baseline_names) & set(candidate_names) else "warning",
                "sample type sets differ: " + detail,
                "<all>",
                "<profile>",
                float(len(candidate_names)),
                float(len(baseline_names)),
                0.0,
            )
        )
    comparable: list[str] = []
    rates_b: list[float] = []
    rates_c: list[float] = []
    for index, (name, _unit) in enumerate(candidate.sample_types):
        if name not in baseline_names:
            continue
        base_index = baseline_names.index(name)
        base_total = baseline.totals[base_index]
        cand_total = candidate.totals[index]
        base_rate = _rate(base_total, baseline.duration_ns)
        cand_rate = _rate(cand_total, candidate.duration_ns)
        rates_b.append(base_rate)
        rates_c.append(cand_rate)
        comparable.append(name)
        label = name + "/" + candidate.sample_types[index][1]
        findings.extend(_quality_findings(baseline, candidate, label))

        if base_total > 0 and cand_total > 0:
            rate_delta = cand_rate - base_rate
            noise = _noise_threshold(base_rate, cand_rate, policy)
            if rate_delta > noise and rate_delta > base_rate * policy.max_total_increase_pct / 100:
                findings.append(
                    _finding(
                        "PROF001",
                        "error",
                        "aggregate sample rate rose " + f"{rate_delta / base_rate * 100:.1f}%",
                        label,
                        "<profile>",
                        cand_rate,
                        base_rate,
                        noise,
                    )
                )

        hot_share = policy.min_hot_share_pct / 100
        keys = sorted(
            set(candidate.self_values[index]) | set(baseline.self_values[base_index])
        )
        for key in keys:
            base_self = baseline.self_values[base_index].get(key, 0)
            cand_self = candidate.self_values[index].get(key, 0)
            base_share = base_self / base_total if base_total > 0 else 0.0
            cand_share = cand_self / cand_total if cand_total > 0 else 0.0
            expected = cand_total * base_share
            delta = cand_self - expected
            noise = _noise_threshold(expected, cand_self, policy)
            if cand_total > 0 and delta > noise and base_self > 0:
                share_growth = (cand_share - base_share) / base_share * 100
                if share_growth > policy.max_frame_increase_pct:
                    findings.append(
                        _finding(
                            "PROF002",
                            "error",
                            "frame self share rose " + f"{share_growth:.1f}%"
                            + " ("
                            + f"{base_share * 100:.2f}%"
                            + " -> "
                            + f"{cand_share * 100:.2f}%"
                            + ")",
                            label,
                            key,
                            cand_self,
                            expected,
                            noise,
                        )
                    )
            if (
                cand_total > 0
                and cand_share >= hot_share
                and cand_self >= policy.min_hot_samples
                and base_self < policy.min_hot_samples
            ):
                findings.append(
                    _finding(
                        "PROF004",
                        "error",
                        "frame became hot without baseline evidence",
                        label,
                        key,
                        cand_self,
                        base_self,
                        float(policy.min_hot_samples),
                    )
                )
            if base_total > 0 and base_share >= hot_share and base_self >= policy.min_hot_samples and cand_self == 0:
                findings.append(
                    _finding(
                        "PROF005",
                        "note",
                        "previously hot frame is absent from candidate",
                        label,
                        key,
                        cand_self,
                        base_self,
                        0.0,
                    )
                )

        cum_keys = sorted(
            set(candidate.cumulative_values[index]) | set(baseline.cumulative_values[base_index])
        )
        for key in cum_keys:
            base_cum = baseline.cumulative_values[base_index].get(key, 0)
            cand_cum = candidate.cumulative_values[index].get(key, 0)
            if base_total <= 0 or cand_total <= 0 or base_cum == 0:
                continue
            base_share = base_cum / base_total
            cand_share = cand_cum / cand_total
            expected = cand_total * base_share
            delta = cand_cum - expected
            noise = _noise_threshold(expected, cand_cum, policy)
            share_growth = (cand_share - base_share) / base_share * 100
            if delta > noise and share_growth > policy.max_frame_increase_pct:
                findings.append(
                    _finding(
                        "PROF003",
                        "warning",
                        "hot-path cumulative share rose " + f"{share_growth:.1f}%",
                        label,
                        key,
                        cand_cum,
                        expected,
                        noise,
                    )
                )

    findings.sort(
        key=lambda item: (
            SEVERITIES.index(item.severity),
            item.rule,
            item.sample_type,
            item.frame,
            item.finding_id,
        )
    )
    return Analysis(
        findings=tuple(findings),
        comparable_types=tuple(comparable),
        baseline_rate=tuple(rates_b),
        candidate_rate=tuple(rates_c),
    )


def should_fail(analysis: Analysis, fail_on: str) -> bool:
    if fail_on == "never":
        return False
    if fail_on == "error":
        return any(item.severity == "error" for item in analysis.findings)
    threshold = SEVERITIES.index(fail_on)
    return any(SEVERITIES.index(item.severity) <= threshold for item in analysis.findings)
