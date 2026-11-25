"""Symbol and stack normalization shared by both sides of a comparison.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config import Policy
from .proto import Frame, ProfileData

_TRUNCATED = "<stack-truncated>"
_UNKNOWN = "<unknown>"


@dataclass(frozen=True)
class AggregatedProfile:
    sample_types: tuple[tuple[str, str], ...]
    totals: tuple[int, ...]
    self_values: tuple[dict[str, int], ...]
    cumulative_values: tuple[dict[str, int], ...]
    display_names: dict[str, str]
    sample_count: int
    negative_values: int
    empty_stacks: int
    truncated_stacks: int
    duration_ns: int
    unknown_frames: int

    def total_for(self, index: int) -> int:
        return self.totals[index]


def normalize_symbol(symbol: str) -> str:
    if not symbol:
        return _UNKNOWN
    result = []
    index = 0
    while index < len(symbol):
        char = symbol[index]
        if char == "[":
            depth = 1
            index += 1
            while index < len(symbol) and depth:
                if symbol[index] == "[":
                    depth += 1
                elif symbol[index] == "]":
                    depth -= 1
                index += 1
            if depth:
                result.append("[")
                index = len(symbol) + 1
            else:
                result.append("[*]")
            continue
        if char == "0" and index + 2 < len(symbol) and symbol[index + 1 : index + 3] == "x7":
            end = index + 2
            while end < len(symbol) and symbol[end] in "0123456789abcdefABCDEF":
                end += 1
            if end - index >= 5:
                result.append("0x*")
                index = end
                continue
        result.append(char)
        index += 1
    value = "".join(result)
    if "::h" in value:
        parts = value.split("::")
        for offset, part in enumerate(parts):
            if len(part) > 3 and part.startswith("h"):
                suffix = part[1:]
                if len(suffix) >= 12 and all(char in "0123456789abcdefABCDEF" for char in suffix):
                    parts[offset] = "h*"
        value = "::".join(parts)
    while "  " in value:
        value = value.replace("  ", " ")
    return value.strip()


def normalize_file(path: str, policy: Policy) -> str:
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    for prefix in policy.strip_prefixes:
        candidate = prefix.replace("\\", "/")
        if normalized.startswith(candidate):
            normalized = normalized[len(candidate) :]
            break
    marker = "/site-packages/"
    if marker in normalized:
        normalized = "<site-packages>/" + normalized.split(marker, 1)[1]
    return normalized


def normalize_frame(frame: Frame, policy: Policy) -> Frame:
    return Frame(
        function=normalize_symbol(frame.function),
        system_name=normalize_symbol(frame.system_name),
        file=normalize_file(frame.file, policy),
        line=frame.line,
        mapping_file=normalize_file(frame.mapping_file, policy),
    )


def frame_key(frame: Frame, policy: Policy) -> str:
    aliases = policy.frame_aliases or {}
    name = aliases.get(frame.function, frame.function)
    if policy.frame_key == "line" and frame.file:
        return name + "@" + frame.file + ":" + str(frame.line)
    if policy.frame_key == "file" and frame.file:
        return name + "@" + os.path.basename(frame.file)
    return name


def normalize_stack(frames: tuple[Frame, ...], policy: Policy) -> tuple[tuple[Frame, ...], bool]:
    result: list[Frame] = []
    previous = ""
    truncated = False
    for raw_frame in frames:
        frame = normalize_frame(raw_frame, policy)
        key = frame_key(frame, policy)
        if key == previous:
            continue
        if len(result) >= policy.max_stack_depth:
            truncated = True
            break
        result.append(frame)
        previous = key
    if truncated:
        result.append(Frame(_TRUNCATED, "", "", 0, ""))
    return tuple(result), truncated


def aggregate(profile: ProfileData, policy: Policy) -> AggregatedProfile:
    type_count = len(profile.sample_types)
    self_values = [dict[str, int]() for _ in range(type_count)]
    cumulative_values = [dict[str, int]() for _ in range(type_count)]
    totals = [0] * type_count
    display_names: dict[str, str] = {}
    negative_values = 0
    empty_stacks = 0
    truncated_stacks = 0
    unknown_frames = 0

    for sample in profile.samples:
        frames, truncated = normalize_stack(sample.frames, policy)
        if not frames:
            empty_stacks += 1
            continue
        if truncated:
            truncated_stacks += 1
        keys: list[str] = []
        for frame in frames:
            key = frame_key(frame, policy)
            keys.append(key)
            display_names.setdefault(key, frame.function)
            if frame.function == _UNKNOWN:
                unknown_frames += 1
        for index, value in enumerate(sample.values):
            totals[index] += value
            if value < 0:
                negative_values += 1
            cumulative_values[index][keys[0]] = cumulative_values[index].get(keys[0], 0) + value
            if keys[0] not in self_values[index]:
                self_values[index][keys[0]] = 0
            self_values[index][keys[0]] += value
            for key in keys[1:]:
                cumulative_values[index][key] = cumulative_values[index].get(key, 0) + value

    return AggregatedProfile(
        sample_types=tuple((item.name, item.unit) for item in profile.sample_types),
        totals=tuple(totals),
        self_values=tuple(self_values),
        cumulative_values=tuple(cumulative_values),
        display_names=display_names,
        sample_count=len(profile.samples),
        negative_values=negative_values,
        empty_stacks=empty_stacks,
        truncated_stacks=truncated_stacks,
        duration_ns=profile.duration_ns,
        unknown_frames=unknown_frames,
    )
