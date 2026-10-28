"""Deterministic running stitches; preserve corners, quantise before export."""
from __future__ import annotations

from math import ceil, hypot, isfinite

from .model import Document, Event, Op, Point, StitchPlan


def _resample_segment(a: Point, b: Point, max_length_mm: float) -> list[Point]:
    distance = hypot(b.x - a.x, b.y - a.y)
    if distance < 1e-10:
        return []
    n = ceil(distance / max_length_mm)
    return [Point(a.x + (b.x - a.x) * i / n, a.y + (b.y - a.y) * i / n)
            for i in range(1, n + 1)]


def _quantise(p: Point) -> tuple[int, int]:
    # All machine events are fixed to the 0.1 mm DST grid at generation time.
    return round(p.x * 10), round(p.y * 10)


def _split_jump(from_xy: tuple[int, int], to_xy: tuple[int, int]) -> list[Event]:
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    steps = ceil(max(abs(dx), abs(dy)) / 121)
    if not steps:
        return []
    moves = []
    origin = from_xy
    for i in range(1, steps + 1):
        x = origin[0] + round(dx * i / steps)
        y = origin[1] + round(dy * i / steps)
        if (x, y) != from_xy:
            moves.append(Event(Op.JUMP, x, y))
        from_xy = (x, y)
    return moves


def generate_running(document: Document, stitch_length_mm: float = 2.5) -> StitchPlan:
    if not isfinite(stitch_length_mm) or not (0.3 <= stitch_length_mm <= 8.0):
        raise ValueError("stitch_length_mm must be between 0.3 and 8 mm")
    events: list[Event] = []
    cursor = (0, 0)
    for stroke in document.strokes:
        if len(stroke.points) < 2:
            raise ValueError(f"Stroke {stroke.name!r} has fewer than two points")
        start = _quantise(stroke.points[0])
        if start != cursor:
            travel = _split_jump(cursor, start)
            events.extend(travel)
            if travel:
                cursor = (travel[-1].x10, travel[-1].y10)
        poly = list(stroke.points)
        if stroke.closed and poly[-1] != poly[0]:
            poly.append(poly[0])
        for a, b in zip(poly, poly[1:]):
            for p in _resample_segment(a, b, stitch_length_mm):
                coord = _quantise(p)
                if coord == cursor:
                    continue
                # A rounded 0.1mm DST-grid displacement can increase by <0.1mm.
                if max(abs(coord[0] - cursor[0]), abs(coord[1] - cursor[1])) > 121:
                    raise ValueError("Running-stitch move exceeds DST representable length")
                events.append(Event(Op.STITCH, *coord))
                if len(events) > 250_000:
                    raise ValueError("Running stitch event limit exceeded")
                cursor = coord
    events.append(Event(Op.END, *cursor))
    return StitchPlan(tuple(events), document.source_sha256)
