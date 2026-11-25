# Architecture — Baysöz Labs <baysozlabs@proton.me>

## System boundary

`baysoz-profilediff` is a single-process, offline library and CLI. Inputs are two pprof profiles (gzip-compressed or plain protobuf) and an optional JSON policy. Output is text, JSON, or SARIF 2.1.0. There are no sockets, services, databases, agents, or local models.

## Component map

```
filesystem ──> proto.py        (bounded gzip + protobuf wire decoder)
                  │
                  ▼
             model dataclasses (SampleType, Frame, Sample, ProfileData)
                  │
                  ▼
             normalize.py      (symbol/file aliasing, recursion collapse, depth cap)
                  │
                  ▼
             AggregatedProfile (totals, self map, cumulative map per sample type)
                  │
                  ▼
             analyze.py        (rate check, share check, hot-frame transitions, quality rules)
                  │
                  ▼
             report.py         (text / JSON / SARIF deterministically ordered)
                  │
                  ▼
             cli.py            (exit 0 pass, 1 findings, 2 invalid input)
```

## 1. `proto.py` — hardened decoder

- Reads at most 64 MiB from disk; gzip decompression is bounded with `GzipFile.read(limit + 1)` to defeat decompression bombs.
- Generic wire parser handles varint (0), fixed64 (1), length-delimited (2), fixed32 (5), rejects wire types 3/4/6/7, zero field numbers, truncated varints, and >10-byte varints.
- Signed int64 values are interpreted from two's-complement varints; negative sample values are preserved and later treated as a quality error (a differenced profile is not a valid input).
- Repeated numeric fields accept both packed and unpacked encodings.
- Unknown fields are skipped and counted, not executed.
- All string-table references are bounds-checked; UTF-8 is strict.
- Limits: 500,000 samples, 1,000,000 locations/fields, 256 frames per sample, 64 labels per sample.
- Submessage parsing is deferred until the string table is complete, because pprof writers emit field 6 after fields that reference it.
- Inline frames (`Location.line`) are flattened leaf-first; missing functions become `<unknown>` frames.

## 2. `normalize.py` — comparable stacks

Normalization makes two profiles from different builds comparable:

- Go generic instantiations collapse `Foo[go.shape.int_0]` to `Foo[*]`.
- Rust legacy hash suffixes `::h<hex>` collapse to `::h*`.
- Hex addresses `0x7f...` collapse to `0x*`.
- Policy `strip_prefixes` and a built-in `/site-packages/` rule canonicalize file paths.
- Policy `frame_aliases` absorbs deliberate symbol renames.
- Consecutive duplicate frames (recursion) collapse; stacks beyond `max_stack_depth` end in `<stack-truncated>` and raise a note finding.
- `frame_key` supports `function`, `file`, and `line` granularity. Self-attribution uses the leaf frame; cumulative attribution uses every frame on the stack.

## 3. `analyze.py` — decision rules

For sample type `t`, baseline total `B`, candidate total `C`, capture durations `dB`, `dC`:

- Rates: `b = B / (dB/1e9)` when duration is positive, otherwise `B`.
- Noise threshold: `N(x, y) = max(min_delta_samples, z * sqrt(x + y + 1))`. Default `min_delta_samples=32`, `z=2.0`.

| Rule | Severity | Condition |
| --- | --- | --- |
| `PROF001` | error | aggregate rate rises more than `max_total_increase_pct` **and** more than `N(b, c)` |
| `PROF002` | error | frame self share rises more than `max_frame_increase_pct` relative **and** sample delta exceeds `N(C*pB, selfC)` |
| `PROF003` | warning | same test on cumulative (hot-path) attribution |
| `PROF004` | error | frame reaches `min_hot_share_pct` with `min_hot_samples` but has no baseline evidence |
| `PROF005` | note | previously hot frame disappears from candidate |
| `PROF006` | error/warning/note | negative values, empty profiles, missing duration, empty stacks, truncation, unknown symbols, sample-type mismatch |

Finding IDs are the first 16 hex characters of SHA-256 over `rule|sample_type|frame_key`. Findings are sorted by severity, rule, sample type, and frame; output contains no clock values.

`fail_on` is `error` by default and can be `warning`, `note`, or `never`. Exit codes: 0 pass, 1 findings at/above threshold, 2 malformed input or policy.

## 4. `report.py` — output contracts

- SARIF 2.1.0: driver metadata carries product, version, and Baysöz Labs attribution; each result carries a logical location, level, rule ID, stable fingerprint, observed/expected/threshold, and attribution.
- JSON: full analysis including comparable sample types, severity counts, and attributed findings.
- Text: deterministic table with an attribution header and a `PASS` line when clean.

## 5. Security properties

See `SECURITY.md`. In short: read-only file access, no dynamic execution, no deserialization of Python/Java objects, strict decoding bounds, and static/security scans in CI.

## 6. Extension points

- Additional profile producers: implement a decoder returning `ProfileData`.
- Additional policies: extend `Policy` and `load_policy` validation.
- Additional rules: add a rule ID and a deterministic finding in `analyze.py`; SARIF descriptors derive from `RULE_DESCRIPTIONS`.

Baysöz Labs <baysozlabs@proton.me>
