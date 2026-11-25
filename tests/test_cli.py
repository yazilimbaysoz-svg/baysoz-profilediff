"""CLI contract tests, including attribution on help and version output.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baysoz_profilediff.cli import main
from baysoz_profilediff.config import ATTRIBUTION
from tests.fixtures import ProfileBuilder

HOT = (("svc.hot", "/srv/app/hot.go", 10), ("svc.main", "/srv/app/main.go", 1))
COLD = (("svc.cold", "/srv/app/cold.go", 20), ("svc.main", "/srv/app/main.go", 1))


def _write(path: Path, count_hot: int, count_cold: int = 0) -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    for _ in range(count_hot):
        builder.add_samples(HOT, (1,))
    for _ in range(count_cold):
        builder.add_samples(COLD, (1,))
    path.write_bytes(builder.build())


@pytest.mark.parametrize(
    "argv",
    [["--version"], ["--help"], ["compare", "--help"], ["inspect", "--help"], ["policy", "--help"]],
)
def test_help_and_version_are_attributed(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    assert ATTRIBUTION in capsys.readouterr().out


def test_inspect_and_compare_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "base.pb.gz"
    candidate = tmp_path / "cand.pb.gz"
    _write(baseline, 100, 100)
    _write(candidate, 100, 900)
    assert main(["inspect", str(baseline)]) == 0
    assert "samples: 200" in capsys.readouterr().out
    assert main(["compare", str(baseline), str(candidate)]) == 1
    output = capsys.readouterr().out
    assert ATTRIBUTION in output
    assert "PROF002" in output


def test_compare_sarif_output_file_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "base.pb.gz"
    candidate = tmp_path / "cand.pb.gz"
    _write(baseline, 100)
    _write(candidate, 100)
    report = tmp_path / "report.sarif"
    assert main(["compare", str(baseline), str(candidate), "--format", "sarif", "--output", str(report)]) == 0
    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["runs"][0]["results"] == []
    assert ATTRIBUTION in document["runs"][0]["tool"]["driver"]["fullName"]
    assert main(["compare", str(baseline), str(candidate), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["attribution"] == ATTRIBUTION


def test_policy_roundtrip_and_fail_on(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    policy_path = tmp_path / "policy.json"
    assert main(["policy", "init", "--output", str(policy_path)]) == 0
    assert ATTRIBUTION in capsys.readouterr().out
    document = json.loads(policy_path.read_text(encoding="utf-8"))
    assert document["attribution"] == ATTRIBUTION
    assert main(["policy", "init", "--output", str(policy_path)]) == 2
    capsys.readouterr()
    assert main(["policy", "show"]) == 0
    assert ATTRIBUTION in capsys.readouterr().out
    baseline = tmp_path / "base.pb.gz"
    candidate = tmp_path / "cand.pb.gz"
    _write(baseline, 100, 100)
    _write(candidate, 100, 900)
    assert main(["compare", str(baseline), str(candidate), "--policy", str(policy_path), "--fail-on", "never"]) == 0
    capsys.readouterr()
    document["frame_key"] = "invalid"
    policy_path.write_text(json.dumps(document), encoding="utf-8")
    assert main(["compare", str(baseline), str(candidate), "--policy", str(policy_path)]) == 2
    assert ATTRIBUTION in capsys.readouterr().err


def test_invalid_input_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.pb.gz"
    bad.write_bytes(b"\xff" * 11)
    assert main(["inspect", str(bad)]) == 2
    assert ATTRIBUTION in capsys.readouterr().err
    missing = tmp_path / "missing.pb.gz"
    assert main(["inspect", str(missing)]) == 2
    capsys.readouterr()
