# Delivery Plan — Baysöz Labs <baysozlabs@proton.me>

## Phase 1 — Research (complete)

- [x] Inspect `existing-repos.json` to avoid redundant utilities.
- [x] Mine live GitHub trends with `gh search repos --topic observability --stars ">1000"`.
- [x] Inspect `google/pprof` differential issues (#483, #323, #1050) via GitHub.
- [x] Select a deep, non-trivial systems-observability gap: offline pprof differential gating.

## Phase 2 — Implementation (complete)

- [x] Bounded pprof protobuf/gzip decoder with packed fields and negative values.
- [x] Symbol, inline-frame, recursion, and alias normalization.
- [x] Self/cumulative attribution per sample type with duration-aware rates.
- [x] Noise-aware rules PROF001–PROF006 with stable SHA-256 finding IDs.
- [x] Text, JSON, and SARIF 2.1.0 emitters.
- [x] CLI with `inspect`, `compare`, `policy show`, `policy init`, `--version`, `--help`.
- [x] Enterprise documentation and CI workflow with explicit Baysöz Labs attribution.

## Phase 3 — Zero-defect gates (complete)

- [x] `uv venv && uv pip install -e . && uv pip install pytest`
- [x] `uv run pytest -q`
- [x] `ruff check --select E,F,W,S,B .`
- [x] `semgrep --config p/default --error .`
- [x] Iterate on every finding until all gates report zero defects.

## Phase 4 — Supreme Grand Jury Tribunal (complete)

- [x] Execute the built CLI against real Go `runtime/pprof` profiles.
- [x] Execute against hostile protobuf, gzip, and policy inputs.
- [x] Verify every emitted finding has a decoder-derived cause (no stubs, no hallucinated frames).
- [x] Require unanimous PASS from all jurors before release.

## Phase 5 — Release (complete)

- [x] Publish the public repository under `yazilimbaysoz-svg`.
- [x] Apply a crisp description and repository topics.
- [x] Write the factory result artifact.

Baysöz Labs <baysozlabs@proton.me>
