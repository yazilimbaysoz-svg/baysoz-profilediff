"""Decoder tests with adversarial protobuf inputs.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import gzip

import pytest

from baysoz_profilediff.proto import ProfileFormatError, decode_profile
from tests.fixtures import (
    ProfileBuilder,
    encode_bytes,
    encode_int,
    encode_varint,
    uniform_profile,
)

ATTRIBUTION = "Baysöz Labs <baysozlabs@proton.me>"


def test_decodes_gzip_and_plain_profiles() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    stack = (("main.hot", "/srv/app/main.go", 12), ("main.main", "/srv/app/main.go", 6))
    for value in (3, 5):
        builder.add_samples(stack, (value,))
    for payload in (builder.build(), builder.build(compressed=False)):
        profile = decode_profile(payload)
        assert profile.sample_count == 2
        assert profile.sample_types[0].name == "cpu/nanoseconds"
        assert profile.samples[0].values == (3,)
        assert profile.samples[0].frames[0].function == "main.hot"
        assert profile.samples[0].frames[0].file == "/srv/app/main.go"
        assert profile.samples[0].frames[0].mapping_file == "/srv/app"
        assert profile.duration_ns == 1_000_000_000
        assert profile.default_sample_type == "cpu/nanoseconds"


def test_decodes_inline_frames_and_negative_values() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("alloc_objects/count", "count")
    location_id = builder.add_stack(
        (("inner.inline", "/srv/app/inline.go", 9), ("outer.caller", "/srv/app/main.go", 3))
    )
    builder.add_sample((location_id,), (-7,))
    profile = decode_profile(builder.build())
    assert profile.samples[0].values == (-7,)
    assert len(profile.samples[0].frames) == 2


def test_decodes_packed_sample_fields_and_unknown_fields() -> None:
    value_type = encode_int(1, 1) + encode_int(2, 2)
    packed_locations = encode_varint(1) + encode_varint(1)
    sample = encode_bytes(1, packed_locations) + encode_bytes(2, encode_varint(11))
    location = encode_int(1, 1) + encode_bytes(4, encode_int(1, 1) + encode_int(2, 7))
    function = encode_int(1, 1) + encode_int(2, 3) + encode_int(4, 4)
    parts = [
        encode_bytes(1, value_type),
        encode_bytes(2, sample),
        encode_bytes(4, location),
        encode_bytes(5, function),
        encode_bytes(6, b""),
        encode_bytes(6, b"cpu"),
        encode_bytes(6, b"ns"),
        encode_bytes(6, b"main.work"),
        encode_bytes(6, b"work.go"),
        encode_int(99, 7),
    ]
    profile = decode_profile(b"".join(parts))
    assert profile.samples[0].values == (11,)
    assert profile.samples[0].frames[0].function == "main.work"
    assert profile.unknown_field_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x1f\x8bnot-gzip",
        b"\xff" * 11,
        b"\x08",
        b"\x0f",
        b"\x1a\x05abcd",
        b"\x1a\x00",
        b"\x09\x80",
        b"\x12\x03\x1a\x01\x01",
    ],
)
def test_rejects_malformed_payloads(payload: bytes) -> None:
    with pytest.raises(ProfileFormatError):
        decode_profile(payload)


def test_rejects_duplicate_locations_and_unknown_location_references() -> None:
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/ns", "ns")
    location_id = builder.add_stack((("work", "work.go", 1),))
    builder.add_sample((location_id,), (1,))
    raw = builder.build(compressed=False)
    location_field = encode_bytes(4, encode_int(1, location_id))
    with pytest.raises(ProfileFormatError, match="duplicate location id"):
        decode_profile(raw + location_field)
    broken = ProfileBuilder()
    broken.add_sample_type("cpu/ns", "ns")
    broken.add_sample((999,), (1,))
    with pytest.raises(ProfileFormatError, match="unknown location id"):
        decode_profile(broken.build())


def test_rejects_oversized_input() -> None:
    with pytest.raises(ProfileFormatError, match="64 MiB"):
        decode_profile(b"\x00" * (64 * 1024 * 1024 + 1))


def test_rejects_decompression_bomb() -> None:
    bomb = gzip.compress(b"\x00" * (64 * 1024 * 1024 + 1), mtime=0)
    with pytest.raises(ProfileFormatError, match="64 MiB"):
        decode_profile(bomb)


def test_attribution_is_exposed_to_library_users() -> None:
    from baysoz_profilediff import ATTRIBUTION as exported

    assert exported == ATTRIBUTION
    assert decode_profile(uniform_profile(1)).sample_count == 1
