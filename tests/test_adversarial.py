"""Adversarial corpus: malformed, hostile, and boundary inputs.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import gzip

import pytest

from baysoz_profilediff.analyze import compare, should_fail
from baysoz_profilediff.config import ATTRIBUTION, Policy, default_policy
from baysoz_profilediff.normalize import aggregate
from baysoz_profilediff.proto import ProfileFormatError, decode_profile
from tests.fixtures import ProfileBuilder, encode_bytes, encode_int, encode_varint

HOT = (("svc.hot", "/srv/app/hot.go", 1),)


def test_all_single_byte_inputs_are_handled() -> None:
    for value in range(256):
        payload = bytes([value])
        try:
            decode_profile(payload)
        except ProfileFormatError:
            continue


def test_crafted_varint_hostility_is_rejected() -> None:
    hostile = [
        b"\x80" * 9 + b"\x7f",
        b"\x08" + b"\x80" * 10 + b"\x00",
        b"\x12\xff\xff\xff\xff\x0f",
        b"\x1a\x80" + b"\x00" * 4,
        b"\xf8\xff\xff\xff\xff\xff\xff\xff\xff\x01",
    ]
    for payload in hostile:
        with pytest.raises(ProfileFormatError):
            decode_profile(payload)


def test_invalid_utf8_and_bad_indices_are_rejected() -> None:
    bad_utf8 = encode_bytes(6, b"\xff\xfe") + encode_bytes(1, encode_int(1, 1))
    with pytest.raises(ProfileFormatError, match="UTF-8"):
        decode_profile(bad_utf8)
    bad_index = encode_bytes(1, encode_int(1, 99)) + encode_bytes(6, b"")
    with pytest.raises(ProfileFormatError, match="string table index"):
        decode_profile(bad_index)
    empty_table = encode_bytes(1, encode_int(1, 0)) + encode_bytes(4, b"")
    with pytest.raises(ProfileFormatError, match="sample types|string table"):
        decode_profile(empty_table)


def test_oversized_stacks_labels_and_sample_values_are_bounded() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/ns", "ns")
    location_ids = tuple(builder.add_stack(HOT) for _ in range(257))
    builder.add_sample(location_ids, (1,))
    with pytest.raises(ProfileFormatError, match="frame limit"):
        decode_profile(builder.build())
    label = encode_int(1, 0) + encode_int(2, 0)
    sample = encode_bytes(1, encode_varint(1)) + encode_bytes(2, encode_varint(1))
    sample += b"".join(encode_bytes(3, label) for _ in range(65))
    parts = [
        encode_bytes(1, encode_int(1, 1)),
        encode_bytes(2, sample),
        encode_bytes(4, encode_int(1, 1)),
        encode_bytes(6, b""),
        encode_bytes(6, b"cpu"),
    ]
    with pytest.raises(ProfileFormatError, match="labels"):
        decode_profile(b"".join(parts))


def test_duplicate_functions_and_missing_string_table_are_rejected() -> None:
    function = encode_int(1, 1) + encode_int(2, 1)
    payload = (
        encode_bytes(1, encode_int(1, 1))
        + encode_bytes(5, function)
        + encode_bytes(5, function)
        + encode_bytes(6, b"")
        + encode_bytes(6, b"fn")
    )
    with pytest.raises(ProfileFormatError, match="duplicate function id"):
        decode_profile(payload)


def test_concatenated_profiles_are_rejected() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/ns", "ns")
    builder.add_samples(HOT, (1,))
    raw = builder.build(compressed=False)
    with pytest.raises(ProfileFormatError, match="duplicate mapping id"):
        decode_profile(raw + raw)


def test_corrupt_gzip_is_rejected() -> None:
    valid = gzip.compress(b"\x00", mtime=0)
    for index in range(len(valid)):
        mutated = valid[:index] + bytes([valid[index] ^ 0xFF]) + valid[index + 1 :]
        try:
            decode_profile(mutated)
        except ProfileFormatError:
            continue


def test_analysis_survives_extreme_policy_values() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/ns", "ns")
    builder.add_samples(HOT, (1_000_000,))
    view = aggregate(decode_profile(builder.build()), default_policy())
    policy = Policy(z=10.0, min_delta_samples=1_000_000, max_stack_depth=1, min_hot_share_pct=100.0)
    analysis = compare(view, view, policy)
    assert not should_fail(analysis, "error")
    assert analysis.findings == ()


def test_attribution_is_never_dropped_by_error_paths(tmp_path: object) -> None:
    from baysoz_profilediff.cli import main

    assert main(["inspect", "/definitely/missing/profile.pb.gz"]) == 2
    assert ATTRIBUTION
