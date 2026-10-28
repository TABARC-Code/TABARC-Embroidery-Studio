"""Tajima DST encoder, supporting needle stitches, jumps, colour stops and END.

DST stores 0.1mm steps with signed balanced-ternary coordinates, max 121 units
per axis. Colour descriptions, machine-specific trim behaviour and thread data
are NOT preserved here. Do not use as an approved production export.
"""
from __future__ import annotations

from dataclasses import dataclass
from .model import Event, Op, StitchPlan


@dataclass(frozen=True)
class DstSummary:
    label: str
    stitch_records: int
    jump_records: int
    position: tuple[int, int]
    bounds: tuple[int, int, int, int]


def _axis_bits(value: int, placements: tuple[tuple[int, int, int], ...]) -> list[int]:
    if abs(value) > 121:
        raise ValueError("DST displacement exceeds ±12.1 mm")
    bits = [0, 0, 0]
    for byte_index, positive, negative in placements:
        digit = value % 3
        if digit == 2:
            digit = -1
        value = (value - digit) // 3
        if digit:
            bits[byte_index] |= positive if digit == 1 else negative
    if value:
        raise ValueError("DST displacement failed balanced-ternary coding")
    return bits


_X = ((0, 0x01, 0x02), (1, 0x01, 0x02), (0, 0x04, 0x08),
      (1, 0x04, 0x08), (2, 0x04, 0x08))
_Y = ((0, 0x80, 0x40), (1, 0x80, 0x40), (0, 0x20, 0x10),
      (1, 0x20, 0x10), (2, 0x20, 0x10))


def encode_record(dx: int, dy: int, opcode: Op) -> bytes:
    if opcode == Op.END:
        if dx or dy:
            raise ValueError("END cannot move the needle")
        return b"\x00\x00\xf3"
    if opcode not in (Op.STITCH, Op.JUMP, Op.COLOUR_CHANGE):
        raise ValueError(f"DST export cannot handle {opcode}")
    if opcode == Op.COLOUR_CHANGE and (dx or dy):
        raise ValueError("DST colour change must not move the needle")
    bx, by = _axis_bits(dx, _X), _axis_bits(dy, _Y)
    result = bytes((bx[0] | by[0], bx[1] | by[1],
                    bx[2] | by[2] | 0x03 | (
                        0x80 if opcode == Op.JUMP else 0xC0 if opcode == Op.COLOUR_CHANGE else 0)))
    return result


def _header(plan: StitchPlan, label: str) -> bytes:
    moves = [e for e in plan.events if e.opcode in (Op.STITCH, Op.JUMP)]
    xs = [0] + [e.x10 for e in moves]
    ys = [0] + [e.y10 for e in moves]
    end = plan.events[-1]
    # DST has +Y upwards; editable geometry and previews have +Y downwards.
    machine_ys = [-y for y in ys]
    name = "".join(char for char in label.upper() if char.isascii() and (
        char.isalnum() or char in "_-"))[:16] or "TABARC"
    # Extents are measured from file-origin (0,0), in 0.1mm.
    fields = [f"LA:{name:<16}", f"ST:{len(plan.events) - 1:7d}",
              f"CO:{sum(e.opcode == Op.COLOUR_CHANGE for e in plan.events):3d}",
              f"+X:{max(xs):5d}", f"-X:{-min(xs):5d}",
              f"+Y:{max(machine_ys):5d}", f"-Y:{-min(machine_ys):5d}",
              f"AX:{end.x10:+6d}", f"AY:{-end.y10:+6d}",
              "MX:+00000", "MY:+00000", "PD:******"]
    text = ("\r".join(fields) + "\r\x1a").encode("ascii")
    if len(text) > 512:
        raise ValueError("DST header size exceeded")
    return text.ljust(512, b" ")


def export_dst(plan: StitchPlan, label: str = "TABARC") -> bytes:
    # Trims/stops have machine-dependent meaning. DST has no portable unique
    # representation for these commands; refuse silent semantic loss.
    if any(e.opcode in (Op.TRIM, Op.STOP) for e in plan.events):
        raise ValueError("DST cannot safely encode explicit TRIM or STOP; export blocked")
    last = (0, 0)
    records = []
    for e in plan.events:
        here = (e.x10, e.y10)
        delta = (here[0] - last[0], here[1] - last[1])
        if e.opcode == Op.END and here != last:
            raise ValueError("END event is not located at final needle position")
        records.append(encode_record(delta[0], -delta[1], e.opcode))
        last = here
    return _header(plan, label) + b"".join(records)


def inspect_dst(data: bytes) -> DstSummary:
    """Small structural reader for diagnostics, NOT an external validation oracle."""
    if len(data) < 515 or not data.startswith(b"LA:") or (len(data) - 512) % 3:
        raise ValueError("Invalid DST length or header")
    label = data[:20].decode("ascii", errors="replace")[3:].strip()
    x, y = 0, 0
    xs, ys = [0], [0]
    stitch, jumps = 0, 0
    found_end = False
    for idx in range(512, len(data), 3):
        a, b, c = data[idx:idx+3]
        if (a, b, c) == (0, 0, 0xF3):
            if idx != len(data) - 3:
                raise ValueError("Extra DST data after END")
            found_end = True
            break
        if c & 0x03 != 0x03:
            raise ValueError("DST synchronisation bits invalid")
        dx = ((a & 0x01) > 0) - ((a & 0x02) > 0)
        dx += 3 * (((b & 0x01) > 0) - ((b & 0x02) > 0))
        dx += 9 * (((a & 0x04) > 0) - ((a & 0x08) > 0))
        dx += 27 * (((b & 0x04) > 0) - ((b & 0x08) > 0))
        dx += 81 * (((c & 0x04) > 0) - ((c & 0x08) > 0))
        dy = ((a & 0x80) > 0) - ((a & 0x40) > 0)
        dy += 3 * (((b & 0x80) > 0) - ((b & 0x40) > 0))
        dy += 9 * (((a & 0x20) > 0) - ((a & 0x10) > 0))
        dy += 27 * (((b & 0x20) > 0) - ((b & 0x10) > 0))
        dy += 81 * (((c & 0x20) > 0) - ((c & 0x10) > 0))
        x += dx
        y -= dy  # Undo DST machine-axis inversion; return screen-space geometry.
        xs.append(x)
        ys.append(y)
        if (c & 0xC0) == 0x80:
            jumps += 1
        elif (c & 0xC0) == 0x00:
            stitch += 1
        elif (c & 0xC0) == 0xC0:
            pass  # Colour stop, not a movement stitch.
        else:
            raise ValueError("Unsupported DST record flag")
    if not found_end:
        raise ValueError("DST file is missing END")
    return DstSummary(label, stitch, jumps, (x, y),
                      (min(xs), min(ys), max(xs), max(ys)))


def read_dst_events(data: bytes) -> tuple[Event, ...]:
    """Decode all recorded needle positions for a stronger round-trip comparison.

    Important: this is still our own codec, not external-format validation.
    """
    inspect_dst(data)  # Header, control-bit and END structural checks.
    current_x = current_y = 0
    events = []
    for offset in range(512, len(data), 3):
        raw = data[offset:offset + 3]
        a, b, c = raw
        if raw == b"\x00\x00\xf3":
            events.append(Event(Op.END, current_x, current_y))
            break
        coordinate_bytes = (a, b, c)
        def decode(mapping: tuple[tuple[int, int, int], ...]) -> int:
            return sum((3 ** order) * (
                bool(coordinate_bytes[index] & plus) - bool(coordinate_bytes[index] & minus))
                for order, (index, plus, minus) in enumerate(mapping))
        current_x += decode(_X)
        current_y -= decode(_Y)
        control = c & 0xC0
        opcode = {0x00: Op.STITCH, 0x80: Op.JUMP, 0xC0: Op.COLOUR_CHANGE}.get(control)
        if opcode is None:
            raise ValueError("Unsupported DST sequin command")
        events.append(Event(opcode, current_x, current_y))
    return tuple(events)
