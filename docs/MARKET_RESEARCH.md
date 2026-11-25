# Market Research — Baysöz Labs <baysozlabs@proton.me>

Project: **baysoz-profilediff** — deterministic, offline, noise-aware pprof differential regression gate with SARIF enforcement.
Research date: 2026-11-25. Sources: `gh search repos`, `gh search issues`, and direct GitHub issue inspection performed for this delivery.

## 1. Ecosystem signal (live GitHub data)

| Repository | Stars (observed) | Role in the ecosystem | Gap relevant to this project |
| --- | ---: | --- | --- |
| `google/pprof` | 9,329 | Reference producer/consumer of `profile.proto`; `go tool pprof -base` is the de facto diff mechanism | Diff is interactive and percentage-based; no CI exit code, no noise model, no stable finding IDs, no SARIF |
| `parca-dev/parca` | 5,025 | Continuous profiling storage and UI | Requires a deployed service; comparisons are exploratory, not policy-gated |
| `parca-dev/parca-agent` | 750 | eBPF always-on profiler | Produces the profiles but does not decide whether a delta is a regression |
| `tikv/pprof-rs` | 1,665 | Rust profiler writing pprof-compatible data | Cross-language profile shapes (inlined frames, generics, mangled symbols) need normalization before comparison |
| `DataDog/go-profiler-notes` | 3,668 | Canonical documentation of profile semantics | Documents that samples, not wall time, drive profiles; confirms why rate normalization matters |
| `profefe/profefe` | 624 | Long-term profile retention | Storage, not analysis or enforcement |
| `netdata/netdata` | 81,615 | Full-stack observability | Visualizes cost; no deterministic per-frame gate for CI |
| `SigNoz/signoz` | 32,733 | OTel-native APM platform | No raw pprof protobuf differential contract |
| `vectordotdev/vector` | 22,958 | Observability data pipeline | Transports telemetry; does not judge profile regressions |
| `Tracer-Cloud/opensre` | 15,217 | CI/CD reliability tooling | Confirms 2026 trend: reliability checks are moving into CI, but profile diffs are absent |

The dominant pattern is **collection and visualization**. The missing layer is a *decision layer* that consumes two raw profiles and emits a reproducible verdict.

## 2. Open pain points in the upstream tracker

- [`google/pprof#483`](https://github.com/google/pprof/issues/483) (open since 2019, still open in 2026): "Differential flamegraph" — `go tool pprof -diff_base A.pb.gz B.pb.gz` fails in the flamegraph view (`TypeError: null is not an object`). Top/Graph/Peek work, but the differential visualization does not. This is a nine-year-old unmet differential workflow in a 9.3k-star tool.
- [`google/pprof#323`](https://github.com/google/pprof/issues/323): "Fix percentage calculation in diff mode (-base)" — historical evidence that even the basic diff percentages were subtly wrong. A gate that simply invokes `pprof -base` inherits that class of defect.
- `google/pprof#1050` (closed 2026-10-15): "proftest: Diff fails tests on identical inputs when diff tool is not in PATH" — demonstrates that diff correctness depends on external tooling availability; an offline decoder removes that dependency.
- Additional ecosystem pain: re-symbolization noise across builds (Go generic instantiations, Rust hash-suffixed symbols, Python `site-packages` paths), differing capture durations, and the absence of a statistically defensible "is this delta noise?" rule.

## 3. Why not a trivial utility

This is not a "compare two numbers" CLI. The implementation must:

1. Decode the **protobuf wire format** directly, including varints, packed repeated fields, length-delimited submessages, gzip containers, negative int64 sample values, and forward-compatible unknown fields.
2. Resolve **string tables, functions, locations, inline frames, and mappings** into a normalized stack model with cycle collapsing and depth bounds.
3. Build **self and cumulative attribution maps per sample type**, not just totals.
4. Apply a **Poisson-style noise threshold** (`max(min_delta_samples, z * sqrt(expected + observed + 1))`) plus a relative-share gate, so a 104-vs-100 sample fluctuation does not fail CI while an 900-vs-100 hot-path shift does.
5. Distinguish **rate** changes using capture duration, so a longer profiling session is not misread as a regression.
6. Emit **SARIF 2.1.0** with stable fingerprints, deterministic ordering, and no timestamps or network calls.

## 4. Differentiation from adjacent Baysöz Labs work

The existing portfolio covers PromQL conformance (`baysoz-queryoracle`), SLO burn policy (`baysoz-burnlattice`), OTel collector config (`baysoz-otelgate`), cardinality (`baysoz-cardinalis`), and trace propagation (`baysoz-tracecontinuity`). None consumes **raw pprof protobuf profiles** or performs **statistical differential attribution**. `baysoz-profilediff` therefore fills a distinct layer of the systems-observability stack: *performance-regression conformance* at CI time.

## 5. Target users and adoption path

- SRE/platform teams running CPU/heap/mutex/block profiles in nightly CI.
- Performance engineering teams needing reproducible evidence for a regression before opening an issue.
- Multi-language shops (Go, Rust, Python) whose profiles share the pprof wire format but not symbol conventions.

Adoption requires only two `.pb.gz` files and `uv tool install .`; there is no agent, collector, database, or LLM in the loop.

## 6. Verdict

A high-value, non-redundant gap exists between profile production (9k-star pprof, 5k-star Parca) and reliability enforcement in CI. `baysoz-profilediff` is a deep, offline, deterministic implementation of that missing decision layer.

Baysöz Labs <baysozlabs@proton.me>
