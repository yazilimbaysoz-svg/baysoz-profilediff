# Security Policy — Baysöz Labs <baysozlabs@proton.me>

## Reporting vulnerabilities

Report security issues privately to **baysozlabs@proton.me**. Do not open a public issue for an exploitable defect. Baysöz Labs <baysozlabs@proton.me> aims to acknowledge reports promptly and coordinate disclosure after a fix is released.

## Threat model

- **Untrusted profile files:** the CLI may be pointed at attacker-supplied `.pb.gz` data in CI.
- **Untrusted policy files:** policies may be contributed by pull requests.
- **No network trust boundary:** the tool performs no network I/O at all.

## Defenses

1. **Bounded resource use:** 64 MiB input cap; bounded gzip streaming; caps on samples, locations, fields, frames per sample, and labels per sample. No unbounded recursion.
2. **Strict wire validation:** invalid wire types, truncated varints, overflowing varints, out-of-range string-table indices, invalid UTF-8, duplicate IDs, and missing stacks are rejected before analysis.
3. **No dynamic execution:** no `eval`, `exec`, `pickle`, `yaml.load`, shells, or subprocesses; profiles are data, never code.
4. **No secret handling:** the tool does not read environment variables, credentials, or tokens. Reports contain only profile-derived symbols and policy-derived strings.
5. **Deterministic analysis:** no timestamps, randomness, or host-specific paths in reports; SARIF fingerprints are SHA-256 derived.
6. **Supply chain:** dependencies are limited to Python 3.13+ standard library at runtime; development tools are pinned by minimum version and scanned in CI with `semgrep --config p/default --error .` and `ruff check --select E,F,W,S,B .`.

## Supported versions

Security fixes are applied to the latest release (1.0.x). Older versions are not maintained.

## Attribution

Baysöz Labs <baysozlabs@proton.me>
