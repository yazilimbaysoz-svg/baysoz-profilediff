"""Minimal pprof protobuf encoder used to build real test fixtures.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field

_MASK64 = (1 << 64) - 1


def encode_varint(value: int) -> bytes:
    number = value & _MASK64 if value < 0 else value
    chunks = bytearray()
    while number >= 0x80:
        chunks.append((number & 0x7F) | 0x80)
        number >>= 7
    chunks.append(number)
    return bytes(chunks)


def encode_key(number: int, wire: int) -> bytes:
    return encode_varint((number << 3) | wire)


def encode_int(number: int, value: int) -> bytes:
    return encode_key(number, 0) + encode_varint(value)


def encode_bytes(number: int, payload: bytes) -> bytes:
    return encode_key(number, 2) + encode_varint(len(payload)) + payload


@dataclass
class ProfileBuilder:
    duration_ns: int = 1_000_000_000
    period: int = 1
    default_sample_type: int = 0
    sample_types: list[tuple[str, str]] = field(default_factory=list)
    functions: list[tuple[int, str, str]] = field(default_factory=list)
    locations: list[tuple[int, tuple[tuple[int, int], ...]]] = field(default_factory=list)
    samples: list[tuple[tuple[int, ...], tuple[int, ...]]] = field(default_factory=list)
    _strings: list[str] = field(default_factory=lambda: [""])

    def string_index(self, value: str) -> int:
        if value not in self._strings:
            self._strings.append(value)
        return self._strings.index(value)

    def add_sample_type(self, name: str, unit: str) -> int:
        self.sample_types.append((name, unit))
        return len(self.sample_types) - 1

    def add_stack(self, frames: tuple[tuple[str, str, int], ...]) -> int:
        lines: list[tuple[int, int]] = []
        for name, filename, line in frames:
            self.functions.append((0, name, filename))
            lines.append((len(self.functions), line))
        self.locations.append((1, tuple(lines)))
        return len(self.locations)

    def add_sample(self, location_ids: tuple[int, ...], values: tuple[int, ...]) -> None:
        self.samples.append((location_ids, values))

    def add_samples(self, frames: tuple[tuple[str, str, int], ...], values: tuple[int, ...]) -> None:
        self.add_sample((self.add_stack(frames),), values)

    def build(self, *, compressed: bool = True, extra: bytes = b"") -> bytes:
        parts: list[bytes] = []
        for name, unit in self.sample_types:
            value_type = encode_int(1, self.string_index(name)) + encode_int(2, self.string_index(unit))
            parts.append(encode_bytes(1, value_type))
        for location_ids, values in self.samples:
            sample = b"".join(encode_int(1, value) for value in location_ids)
            sample += encode_bytes(2, b"".join(encode_varint(value) for value in values))
            parts.append(encode_bytes(2, sample))
        mapping = (
            encode_int(1, 1)
            + encode_int(2, 0)
            + encode_int(3, 0)
            + encode_bytes(5, b"/srv/app")
            + encode_bytes(6, b"build-id-1")
        )
        parts.append(encode_bytes(3, mapping))
        for index, (mapping_id, lines) in enumerate(self.locations, start=1):
            location = (
                encode_int(1, index)
                + encode_int(2, mapping_id)
                + encode_int(3, index * 16)
            )
            for function_id, line in lines:
                location += encode_bytes(4, encode_int(1, function_id) + encode_int(2, line))
            parts.append(encode_bytes(4, location))
        for index, (_function_id, name, filename) in enumerate(self.functions, start=1):
            function = (
                encode_int(1, index)
                + encode_int(2, self.string_index(name))
                + encode_int(3, self.string_index(name))
                + encode_int(4, self.string_index(filename))
                + encode_int(5, 0)
            )
            parts.append(encode_bytes(5, function))
        for value in self._strings:
            parts.append(encode_bytes(6, value.encode("utf-8")))
        parts.append(encode_int(10, self.duration_ns))
        parts.append(encode_int(12, self.period))
        parts.append(encode_int(14, self.default_sample_type))
        parts.append(extra)
        raw = b"".join(parts)
        return gzip.compress(raw, mtime=0) if compressed else raw


def uniform_profile(value: int, frames: tuple[tuple[str, str, int], ...] | None = None) -> bytes:
    frames = frames or (("main.hot", "/srv/app/main.go", 10), ("main.main", "/srv/app/main.go", 4))
    builder = ProfileBuilder()
    builder.add_sample_type("cpu/nanoseconds", "nanoseconds")
    for _ in range(value):
        builder.add_samples(frames, (1,))
    return builder.build()
