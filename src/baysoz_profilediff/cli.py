"""Command line interface for the Baysöz Labs pprof differential gate.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import Analysis, compare, should_fail
from .config import (
    ATTRIBUTION,
    FAIL_ON_LEVELS,
    PRODUCT,
    VERSION,
    PolicyError,
    default_policy,
    load_policy,
    policy_document,
)
from .normalize import aggregate
from .proto import ProfileData, ProfileFormatError, decode_profile
from .report import render_inspect, render_json, render_sarif, render_text

EXIT_PASS = 0
EXIT_FINDINGS = 1
EXIT_INPUT_ERROR = 2
FORMATS = ("text", "json", "sarif")


def _version_text() -> str:
    return PRODUCT + " " + VERSION + " — " + ATTRIBUTION


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profilediff",
        description=(
            "Deterministic offline pprof differential regression gate. "
            "Built by " + ATTRIBUTION + "."
        ),
        epilog="Baysöz Labs <baysozlabs@proton.me> | systems-observability tooling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_version_text(),
        help="show version and Baysöz Labs attribution",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect",
        help="inspect profile structure without network access",
        description="Inspect a pprof profile. " + ATTRIBUTION + ".",
        epilog=ATTRIBUTION,
    )
    inspect.add_argument("profile", type=Path, help="plain or gzip-compressed pprof profile")
    inspect.add_argument("--format", choices=FORMATS, default="text")

    compare_parser = subparsers.add_parser(
        "compare",
        help="compare baseline and candidate profiles",
        description="Noise-aware differential analysis. " + ATTRIBUTION + ".",
        epilog=ATTRIBUTION,
    )
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    compare_parser.add_argument("--policy", type=Path, help="JSON policy document")
    compare_parser.add_argument("--format", choices=FORMATS, default="text")
    compare_parser.add_argument("--output", type=Path, help="write report to a file")
    compare_parser.add_argument("--fail-on", choices=FAIL_ON_LEVELS, default=None)

    policy = subparsers.add_parser(
        "policy",
        help="show or write the default policy",
        description="Policy management. " + ATTRIBUTION + ".",
        epilog=ATTRIBUTION,
    )
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    show = policy_sub.add_parser("show", help="print the default policy", epilog=ATTRIBUTION)
    show.add_argument("--format", choices=("json",), default="json")
    init = policy_sub.add_parser("init", help="write the default policy", epilog=ATTRIBUTION)
    init.add_argument("--output", type=Path, default=Path("profilediff-policy.json"))
    init.add_argument("--force", action="store_true")
    return parser


def _decode(path: Path) -> ProfileData:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProfileFormatError("cannot read profile " + str(path) + ": " + str(exc)) from exc
    return decode_profile(raw)


def _emit(text: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(text)
        return
    try:
        output.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ProfileFormatError("cannot write report: " + str(exc)) from exc


def _inspect(args: argparse.Namespace) -> int:
    profile = _decode(args.profile)
    if args.format == "json":
        document = {
            "tool": PRODUCT,
            "version": VERSION,
            "attribution": ATTRIBUTION,
            "path": str(args.profile),
            "samples": profile.sample_count,
            "duration_ns": profile.duration_ns,
            "default_sample_type": profile.default_sample_type,
            "sample_types": [
                {"name": name, "unit": unit} for name, unit in profile.sample_types
            ],
            "mappings": profile.mapping_count,
        }
        sys.stdout.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_inspect(profile, str(args.profile)))
    return EXIT_PASS


def _compare(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    baseline = aggregate(_decode(args.baseline), policy)
    candidate = aggregate(_decode(args.candidate), policy)
    analysis: Analysis = compare(baseline, candidate, policy)
    if args.format == "sarif":
        text = render_sarif(analysis)
    elif args.format == "json":
        text = render_json(analysis)
    else:
        text = render_text(analysis)
    _emit(text, args.output)
    if should_fail(analysis, args.fail_on or policy.fail_on):
        return EXIT_FINDINGS
    return EXIT_PASS


def _policy(args: argparse.Namespace) -> int:
    document = policy_document(default_policy())
    text = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.policy_command == "show":
        sys.stdout.write(text)
        return EXIT_PASS
    if args.output.exists() and not args.force:
        raise PolicyError("policy file already exists; use --force to overwrite")
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise PolicyError("cannot write policy: " + str(exc)) from exc
    sys.stdout.write("policy written to " + str(args.output) + " by " + ATTRIBUTION + "\n")
    return EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            return _inspect(args)
        if args.command == "compare":
            return _compare(args)
        return _policy(args)
    except (ProfileFormatError, PolicyError) as exc:
        sys.stderr.write(PRODUCT + ": error: " + str(exc) + " | " + ATTRIBUTION + "\n")
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
