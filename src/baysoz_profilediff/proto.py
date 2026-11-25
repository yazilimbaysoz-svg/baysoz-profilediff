"""Hardened decoder for Google pprof protobuf profiles.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import gzip
import io
import zlib
from dataclasses import dataclass

MAX_PROFILE_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 500_000
MAX_LOCATIONS = 1_000_000
MAX_FRAMES_PER_SAMPLE = 256
MAX_LABELS_PER_SAMPLE = 64

_GZIP_MAGIC = b"\x1f\x8b"
_UINT64_MODULUS = 1 << 64


class ProfileFormatError(ValueError):
    """Raised when a profile is malformed or exceeds decoding limits."""


@dataclass(frozen=True)
class _Field:
    number: int
    wire: int
    value: int | bytes


def _decode_varint(data: bytes, pos: int, end: int) -> tuple[int, int]:
    result = 0
    shift = 0
    for _ in range(10):
        if pos >= end:
            raise ProfileFormatError("truncated varint")
        byte = data[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise ProfileFormatError("varint overflow")
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7
    raise ProfileFormatError("varint exceeds 10 bytes")


def _as_signed(value: int) -> int:
    return value - _UINT64_MODULUS if value >= (_UINT64_MODULUS >> 1) else value


def _iter_fields(data: bytes) -> list[_Field]:
    fields: list[_Field] = []
    pos = 0
    end = len(data)
    while pos < end:
        key, pos = _decode_varint(data, pos, end)
        number = key >> 3
        wire = key & 7
        if number == 0:
            raise ProfileFormatError("field number zero is invalid")
        if wire == 0:
            value, pos = _decode_varint(data, pos, end)
        elif wire == 1:
            if end - pos < 8:
                raise ProfileFormatError("truncated fixed64 field")
            value = data[pos : pos + 8]
            pos += 8
        elif wire == 2:
            length, pos = _decode_varint(data, pos, end)
            if length > end - pos:
                raise ProfileFormatError("truncated length-delimited field")
            value = data[pos : pos + length]
            pos += length
        elif wire == 5:
            if end - pos < 4:
                raise ProfileFormatError("truncated fixed32 field")
            value = data[pos : pos + 4]
            pos += 4
        else:
            raise ProfileFormatError("unsupported protobuf wire type: " + str(wire))
        fields.append(_Field(number=number, wire=wire, value=value))
        if len(fields) > MAX_LOCATIONS:
            raise ProfileFormatError("too many protobuf fields")
    return fields


def _repeated_numbers(field: _Field, *, signed: bool) -> list[int]:
    if field.wire == 0:
        raw = [int(field.value)]
    elif field.wire == 2:
        payload = bytes(field.value)
        raw = []
        pos = 0
        while pos < len(payload):
            number, pos = _decode_varint(payload, pos, len(payload))
            raw.append(number)
    else:
        raise ProfileFormatError("numeric field has incompatible wire type")
    return [_as_signed(number) if signed else number for number in raw]


def _text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileFormatError("invalid UTF-8 string in profile") from exc


def _table_string(table: tuple[str, ...], index: int) -> str:
    if index < 0 or index >= len(table):
        raise ProfileFormatError("string table index out of range: " + str(index))
    return table[index]


@dataclass(frozen=True)
class Label:
    key: str
    value: str
    numeric: int
    unit: str


@dataclass(frozen=True)
class Frame:
    function: str
    system_name: str
    file: str
    line: int
    mapping_file: str


@dataclass(frozen=True)
class Sample:
    frames: tuple[Frame, ...]
    values: tuple[int, ...]
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class SampleType:
    name: str
    unit: str


@dataclass(frozen=True)
class ProfileData:
    sample_types: tuple[SampleType, ...]
    samples: tuple[Sample, ...]
    default_sample_type: str
    period_type: SampleType
    period: int
    time_ns: int
    duration_ns: int
    comments: tuple[str, ...]
    drop_frames: int
    keep_frames: int
    mapping_count: int
    unknown_field_count: int

    @property
    def sample_count(self) -> int:
        return len(self.samples)


def _maybe_decompress(raw: bytes) -> bytes:
    if len(raw) > MAX_PROFILE_BYTES:
        raise ProfileFormatError("input file exceeds 64 MiB limit")
    if not raw.startswith(_GZIP_MAGIC):
        return raw
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            data = stream.read(MAX_PROFILE_BYTES + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise ProfileFormatError("invalid gzip container: " + str(exc)) from exc
    if len(data) > MAX_PROFILE_BYTES:
        raise ProfileFormatError("decompressed profile exceeds 64 MiB limit")
    return data


def _parse_value_type(data: bytes, table: tuple[str, ...]) -> SampleType:
    name_index = 0
    unit_index = 0
    for field in _iter_fields(data):
        if field.number == 1 and field.wire == 0:
            name_index = _as_signed(int(field.value))
        elif field.number == 2 and field.wire == 0:
            unit_index = _as_signed(int(field.value))
    return SampleType(_table_string(table, name_index), _table_string(table, unit_index))

def _parse_label(data: bytes, table: tuple[str, ...]) -> Label:
    key_index = 0
    str_index = 0
    num = 0
    unit_index = 0
    for field in _iter_fields(data):
        if field.number == 1 and field.wire == 0:
            key_index = _as_signed(int(field.value))
        elif field.number == 2 and field.wire == 0:
            str_index = _as_signed(int(field.value))
        elif field.number == 3 and field.wire == 0:
            num = _as_signed(int(field.value))
        elif field.number == 4 and field.wire == 0:
            unit_index = _as_signed(int(field.value))
    return Label(
        key=_table_string(table, key_index),
        value=_table_string(table, str_index),
        numeric=num,
        unit=_table_string(table, unit_index),
    )


def _parse_mapping(data: bytes) -> tuple[int, str, str]:
    mapping_id = 0
    file = ""
    build_id = ""
    for field in _iter_fields(data):
        if field.number == 1 and field.wire == 0:
            mapping_id = int(field.value)
        elif field.number == 5 and field.wire == 2:
            file = _text(bytes(field.value))
        elif field.number == 6 and field.wire == 2:
            build_id = _text(bytes(field.value))
    return mapping_id, file, build_id


def _parse_function(data: bytes, table: tuple[str, ...]) -> tuple[int, str, str, str, int]:
    function_id = 0
    name_index = 0
    system_index = 0
    filename_index = 0
    start_line = 0
    for field in _iter_fields(data):
        if field.number == 1 and field.wire == 0:
            function_id = int(field.value)
        elif field.number == 2 and field.wire == 0:
            name_index = _as_signed(int(field.value))
        elif field.number == 3 and field.wire == 0:
            system_index = _as_signed(int(field.value))
        elif field.number == 4 and field.wire == 0:
            filename_index = _as_signed(int(field.value))
        elif field.number == 5 and field.wire == 0:
            start_line = _as_signed(int(field.value))
    return (
        function_id,
        _table_string(table, name_index),
        _table_string(table, system_index),
        _table_string(table, filename_index),
        start_line,
    )


def _parse_location(data: bytes) -> tuple[int, int, int, list[tuple[int, int]]]:
    location_id = 0
    mapping_id = 0
    address = 0
    lines: list[tuple[int, int]] = []
    for field in _iter_fields(data):
        if field.number == 1 and field.wire == 0:
            location_id = int(field.value)
        elif field.number == 2 and field.wire == 0:
            mapping_id = int(field.value)
        elif field.number == 3 and field.wire == 0:
            address = int(field.value)
        elif field.number == 4 and field.wire == 2:
            function_id = 0
            line = 0
            for line_field in _iter_fields(bytes(field.value)):
                if line_field.number == 1 and line_field.wire == 0:
                    function_id = int(line_field.value)
                elif line_field.number == 2 and line_field.wire == 0:
                    line = _as_signed(int(line_field.value))
            lines.append((function_id, line))
    return location_id, mapping_id, address, lines


def _parse_sample(
    data: bytes,
    table: tuple[str, ...],
    locations: dict[int, tuple[int, int, list[tuple[int, int]]]],
    functions: dict[int, tuple[str, str, str, int]],
    mappings: dict[int, str],
    sample_type_count: int,
) -> Sample:
    location_ids: list[int] = []
    values: list[int] = []
    labels: list[Label] = []
    for field in _iter_fields(data):
        if field.number == 1:
            location_ids.extend(_repeated_numbers(field, signed=False))
        elif field.number == 2:
            values.extend(_repeated_numbers(field, signed=True))
        elif field.number == 3 and field.wire == 2:
            if len(labels) >= MAX_LABELS_PER_SAMPLE:
                raise ProfileFormatError("too many labels in a sample")
            labels.append(_parse_label(bytes(field.value), table))
    if len(location_ids) > MAX_FRAMES_PER_SAMPLE:
        raise ProfileFormatError("sample stack exceeds frame limit")
    if not values:
        raise ProfileFormatError("sample has no values")
    if sample_type_count and len(values) != sample_type_count:
        raise ProfileFormatError("sample value count does not match sample type count")
    frames: list[Frame] = []
    for location_id in location_ids:
        location = locations.get(location_id)
        if location is None:
            raise ProfileFormatError("sample refers to unknown location id")
        mapping_id, _address, lines = location
        if not lines:
            frames.append(Frame("<unknown>", "", "", 0, mappings.get(mapping_id, "")))
            continue
        for function_id, line in lines:
            function = functions.get(function_id)
            if function is None:
                frames.append(Frame("<unknown>", "", "", line, mappings.get(mapping_id, "")))
            else:
                frames.append(
                    Frame(
                        function=function[0],
                        system_name=function[1],
                        file=function[2],
                        line=line,
                        mapping_file=mappings.get(mapping_id, ""),
                    )
                )
    return Sample(frames=tuple(frames), values=tuple(values), labels=tuple(labels))


def decode_profile(raw: bytes) -> ProfileData:
    """Decode a raw pprof protobuf profile, gzip-compressed or plain."""
    data = _maybe_decompress(raw)
    if not data:
        raise ProfileFormatError("empty profile payload")
    top_level = _iter_fields(data)
    string_table: list[str] = []
    raw_sample_types: list[bytes] = []
    raw_functions: list[bytes] = []
    raw_period_type: bytes | None = None
    raw_samples: list[bytes] = []
    mappings: dict[int, str] = {}
    locations: dict[int, tuple[int, int, list[tuple[int, int]]]] = {}
    functions: dict[int, tuple[str, str, str, int]] = {}
    comments: list[int] = []
    time_ns = 0
    duration_ns = 0
    period = 0
    period_type = SampleType("", "")
    drop_frames = 0
    keep_frames = 0
    default_sample_type = 0
    unknown_fields = 0
    known_fields = {
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14
    }

    for field in top_level:
        if field.number not in known_fields:
            unknown_fields += 1
        elif field.number == 1 and field.wire == 2:
            raw_sample_types.append(bytes(field.value))
        elif field.number == 2 and field.wire == 2:
            if len(raw_samples) >= MAX_SAMPLES:
                raise ProfileFormatError("too many samples")
            raw_samples.append(bytes(field.value))
        elif field.number == 3 and field.wire == 2:
            mapping_id, file, _build_id = _parse_mapping(bytes(field.value))
            if mapping_id in mappings:
                raise ProfileFormatError("duplicate mapping id")
            mappings[mapping_id] = file
        elif field.number == 4 and field.wire == 2:
            location_id, mapping_id, _address, lines = _parse_location(bytes(field.value))
            if location_id in locations:
                raise ProfileFormatError("duplicate location id")
            if len(locations) >= MAX_LOCATIONS:
                raise ProfileFormatError("too many locations")
            locations[location_id] = (mapping_id, _address, lines)
        elif field.number == 5 and field.wire == 2:
            raw_functions.append(bytes(field.value))
        elif field.number == 6 and field.wire == 2:
            string_table.append(_text(bytes(field.value)))
        elif field.number == 7 and field.wire == 0:
            drop_frames = _as_signed(int(field.value))
        elif field.number == 8 and field.wire == 0:
            keep_frames = _as_signed(int(field.value))
        elif field.number == 9 and field.wire == 0:
            time_ns = _as_signed(int(field.value))
        elif field.number == 10 and field.wire == 0:
            duration_ns = _as_signed(int(field.value))
        elif field.number == 11 and field.wire == 2:
            raw_period_type = bytes(field.value)
        elif field.number == 12 and field.wire == 0:
            period = _as_signed(int(field.value))
        elif field.number == 13:
            comments.extend(_repeated_numbers(field, signed=True))
        elif field.number == 14 and field.wire == 0:
            default_sample_type = _as_signed(int(field.value))

    if not string_table:
        raise ProfileFormatError("profile has no string table")
    if string_table[0] != "":
        raise ProfileFormatError("string table must start with an empty string")
    if not raw_sample_types:
        raise ProfileFormatError("profile has no sample types")
    table = tuple(string_table)
    sample_types = [_parse_value_type(payload, table) for payload in raw_sample_types]
    for payload in raw_functions:
        parsed_function = _parse_function(payload, table)
        function_id = parsed_function[0]
        if function_id in functions:
            raise ProfileFormatError("duplicate function id")
        functions[function_id] = parsed_function[1:]
    if raw_period_type is not None:
        period_type = _parse_value_type(raw_period_type, table)
    samples = tuple(
        _parse_sample(payload, table, locations, functions, mappings, len(sample_types))
        for payload in raw_samples
    )
    if default_sample_type < 0 or default_sample_type >= len(sample_types):
        default_name = sample_types[0].name
    else:
        default_name = sample_types[default_sample_type].name
    return ProfileData(
        sample_types=tuple(sample_types),
        samples=samples,
        default_sample_type=default_name,
        period_type=period_type,
        period=period,
        time_ns=time_ns,
        duration_ns=duration_ns,
        comments=tuple(_table_string(table, value) for value in comments),
        drop_frames=drop_frames,
        keep_frames=keep_frames,
        mapping_count=len(mappings),
        unknown_field_count=unknown_fields,
    )
