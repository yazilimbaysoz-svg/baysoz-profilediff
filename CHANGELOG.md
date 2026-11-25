# Changelog — Baysöz Labs <baysozlabs@proton.me>

All notable changes to `baysoz-profilediff` are documented here. Maintained by Baysöz Labs <baysozlabs@proton.me>.

## [1.0.0] - 2026-11-25

### Added

- Hardened pure-Python decoder for plain and gzip-compressed pprof protobuf profiles, including packed repeated fields, inline frames, and negative sample values.
- Symbol and stack normalization for Go generics, Rust hash suffixes, Python site-packages paths, recursion, and configurable aliases.
- Self and cumulative attribution maps per sample type with capture-duration-aware rate comparison.
- Noise-aware differential rules `PROF001`–`PROF006` with SHA-256 stable finding IDs and configurable thresholds.
- Deterministic text, JSON, and SARIF 2.1.0 reporters.
- CLI commands `inspect`, `compare`, `policy show`, and `policy init` with attributed `--version` and `--help`.
- Adversarial test corpus, CI quality gates, and security policy.

### Changed

- Initial public release.

Baysöz Labs <baysozlabs@proton.me>
