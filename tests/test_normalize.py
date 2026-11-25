"""Stack normalization and aggregation tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from baysoz_profilediff.config import Policy, default_policy
from baysoz_profilediff.normalize import aggregate, frame_key, normalize_file, normalize_stack, normalize_symbol
from baysoz_profilediff.proto import Frame, decode_profile
from tests.fixtures import ProfileBuilder


def _frames(*names: str) -> tuple[Frame, ...]:
    return tuple(Frame(name, name, "/srv/app/app.go", 1, "/srv/app") for name in names)


def test_symbol_normalization_is_deterministic() -> None:
    assert normalize_symbol("main.Worker[go.shape.int_0]") == "main.Worker[*]"
    assert normalize_symbol("pkg::run::h1a2b3c4d5e6f7a8b") == "pkg::run::h*"
    assert normalize_symbol("mod.func at 0x7f1234abcd") == "mod.func at 0x*"
    assert normalize_symbol("  spaced   name ") == "spaced name"
    assert normalize_symbol("") == "<unknown>"
    assert normalize_symbol("pkg.Func[a[b]]") == "pkg.Func[*]"


def test_file_normalization_uses_policy_prefixes() -> None:
    policy = Policy(strip_prefixes=("/srv/app/",))
    assert normalize_file("/srv/app/pkg/work.go", policy) == "pkg/work.go"
    normalized = normalize_file("/usr/lib/python313/site-packages/pkg/mod.py", default_policy())
    assert normalized == "<site-packages>/pkg/mod.py"


def test_stack_normalization_collapses_recursion_and_truncates() -> None:
    policy = Policy(max_stack_depth=3)
    frames, truncated = normalize_stack(_frames("a", "a", "b", "c"), policy)
    assert not truncated
    assert [frame.function for frame in frames] == ["a", "b", "c"]
    frames, truncated = normalize_stack(_frames("a", "b", "c", "d"), policy)
    assert truncated
    assert frames[-1].function == "<stack-truncated>"


def test_frame_keys_respect_policy_modes_and_aliases() -> None:
    frame = Frame("old::run", "old::run", "/srv/app/run.go", 17, "/srv/app")
    aliased = Policy(frame_aliases={"old::run": "new::run"})
    assert frame_key(frame, default_policy()) == "old::run"
    assert frame_key(frame, aliased) == "new::run"
    assert frame_key(frame, Policy(frame_key="file")) == "old::run@run.go"
    assert frame_key(frame, Policy(frame_key="line")) == "old::run@/srv/app/run.go:17"


def test_aggregate_builds_self_and_cumulative_maps() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/ns", "ns")
    leaf = builder.add_stack((("hot", "hot.go", 1),))
    root = builder.add_stack((("cold", "cold.go", 2), ("main", "main.go", 3)))
    builder.add_sample((leaf,), (4,))
    builder.add_sample((root,), (6,))
    view = aggregate(decode_profile(builder.build()), default_policy())
    assert view.totals == (10,)
    assert view.self_values[0] == {"hot": 4, "cold": 6}
    assert view.cumulative_values[0]["main"] == 6
    assert view.cumulative_values[0]["cold"] == 6
    assert view.display_names["hot"] == "hot"
    assert view.negative_values == 0
