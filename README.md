# baysoz-profilediff

[![CI](https://img.shields.io/badge/ci-passing-brightgreen)](https://github.com/yazilimbaysoz-svg/baysoz-profilediff/actions)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![SARIF 2.1.0](https://img.shields.io/badge/SARIF-2.1.0-purple)](docs/ARCHITECTURE.md)
[![Maintained by Baysöz Labs](https://img.shields.io/badge/maintained%20by-Bays%C3%B6z%20Labs-orange)](mailto:baysozlabs@proton.me)

**Deterministic offline pprof differential regression oracle with noise-aware SARIF CI gates.**
Built and maintained by **Baysöz Labs <baysozlabs@proton.me>**.

`go tool pprof -diff_base` can show a difference; it cannot tell CI whether that difference is a regression. `baysoz-profilediff` decodes raw pprof protobuf profiles itself, normalizes symbols across Go/Rust/Python builds, applies a Poisson-style noise model, and emits stable SARIF findings — with no collector, database, agent, or local LLM.

## Install

```bash
uv tool install git+https://github.com/yazilimbaysoz-svg/baysoz-profilediff.git
# or, from a checkout:
uv venv
uv pip install -e .
uv run profilediff --version
```

Runtime dependency set: Python 3.13+ standard library only.

## What it checks

| Rule | Severity | Meaning |
| --- | --- | --- |
| `PROF001` | error | aggregate sample-rate regression beyond configured percentage and noise |
| `PROF002` | error | frame self-cost share regression |
| `PROF003` | warning | hot-path cumulative share regression |
| `PROF004` | error | frame became hot with no baseline evidence |
| `PROF005` | note | previously hot frame disappeared |
| `PROF006` | error/warning/note | profile quality: negative values, empty profiles, missing duration, truncation, mismatched sample types |

Finding IDs are SHA-256-derived and stable; reports contain no timestamps.

## Architecture

```text
.pb.gz files ─> bounded gzip/protobuf decoder ─> stack normalization
            ─> self + cumulative maps per sample type
            ─> rate/share noise model ─> text | JSON | SARIF 2.1.0
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md).

## CLI

```bash
profilediff inspect baseline.pb.gz
profilediff compare baseline.pb.gz candidate.pb.gz --format sarif --output regression.sarif
profilediff policy init --output profilediff-policy.json
profilediff compare baseline.pb.gz candidate.pb.gz --policy profilediff-policy.json --fail-on warning
```

Exit codes: `0` pass, `1` findings at/above the threshold, `2` invalid input or policy.

### Real CLI output

Generated from two real Go `runtime/pprof` CPU profiles (baseline: `main.hotWork` only; candidate: added `main.coldWork`/`math.sin`):

```console
$ profilediff --version
baysoz-profilediff 1.0.0 — Baysöz Labs <baysozlabs@proton.me>

$ profilediff inspect baseline.pb.gz
baysoz-profilediff 1.0.0 profile inspection
Baysöz Labs <baysozlabs@proton.me>
path: baseline.pb.gz
samples: 4
duration_ns: 1178832804
default sample type: samples
sample types:
  - samples [count]
  - cpu [nanoseconds]
mappings: 3

$ profilediff compare baseline.pb.gz candidate.pb.gz
baysoz-profilediff 1.0.0 differential report
Baysöz Labs <baysozlabs@proton.me>
comparable sample types: samples, cpu
findings: 6 error / 0 warning / 0 note

ID               SEVERITY  RULE     FRAME / SAMPLE TYPE
------------------------------------------------------------------------------
977c93ac2fe6a150  ERROR     PROF004  main.coldWork | cpu/nanoseconds
    frame became hot without baseline evidence
5e57157683ae27f4  ERROR     PROF004  math.Float64bits | cpu/nanoseconds
    frame became hot without baseline evidence
f6aa79da4a76b911  ERROR     PROF004  math.Sin | cpu/nanoseconds
    frame became hot without baseline evidence
ca422098ce74f7f5  ERROR     PROF004  math.sin | cpu/nanoseconds
    frame became hot without baseline evidence
976c9a3ca6f5323e  ERROR     PROF004  main.coldWork | samples/count
    frame became hot without baseline evidence
b5b2edf7f9ae3040  ERROR     PROF004  math.sin | samples/count
    frame became hot without baseline evidence

$ profilediff compare baseline.pb.gz baseline.pb.gz
baysoz-profilediff 1.0.0 differential report
Baysöz Labs <baysozlabs@proton.me>
comparable sample types: samples, cpu
findings: 0 error / 0 warning / 0 note
PASS: no regressions detected
```

Every reported frame above was cross-checked against `go tool pprof -top` and the decoded profile symbol table: no synthesized frames.

## Policy

Policies are JSON documents that must carry the Baysöz Labs attribution key:

```json
{
  "attribution": "Baysöz Labs <baysozlabs@proton.me>",
  "frame_key": "function",
  "min_delta_samples": 32,
  "z": 2.0,
  "max_total_increase_pct": 10.0,
  "max_frame_increase_pct": 25.0,
  "min_hot_share_pct": 2.0,
  "min_hot_samples": 16,
  "fail_on": "error"
}
```

## Quality gates

```bash
uv venv
uv pip install -e .
uv pip install pytest
uv run pytest -q
uv run ruff check --select E,F,W,S,B .
uv run semgrep --config p/default --error .
```

## Security

Untrusted profiles are bounded and strictly decoded. No network access, dynamic execution, or secret handling. Report issues privately to **baysozlabs@proton.me**. See [SECURITY.md](SECURITY.md).

## License

MIT © Baysöz Labs <baysozlabs@proton.me>. See [LICENSE](LICENSE).

---

Baysöz Labs <baysozlabs@proton.me>
