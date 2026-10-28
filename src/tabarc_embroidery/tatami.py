"""Scanline tatami prototype with nested contours and holes.

Explicit contours, even-odd containment and jump-only gaps. This is a basic
parallel fill, without underlay, compensation, routing optimisation or trims.
"""
from __future__ import annotations

from math import cos, sin, radians, isfinite, hypot, floor, ceil

from .model import Point, StitchPlan
from .stitch_builder import StitchBuilder, quantise

Ring = tuple[Point, ...]


def _area(ring: Ring) -> float:
    return sum(a.x * b.y - b.x * a.y for a, b in
               zip(ring, ring[1:] + ring[:1])) / 2


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return abs(_orient(a, b, p)) < 1e-8 and (
        min(a.x, b.x) - 1e-8 <= p.x <= max(a.x, b.x) + 1e-8 and
        min(a.y, b.y) - 1e-8 <= p.y <= max(a.y, b.y) + 1e-8)


def _intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    x, y = _orient(a, b, c), _orient(a, b, d)
    z, w = _orient(c, d, a), _orient(c, d, b)
    return ((x * y < -1e-9 and z * w < -1e-9) or
            _on_segment(a, b, c) or _on_segment(a, b, d) or
            _on_segment(c, d, a) or _on_segment(c, d, b))


def _edges(ring: Ring):
    return zip(ring, ring[1:] + ring[:1])


def _inside(point: Point, ring: Ring) -> bool:
    inside = False
    for a, b in _edges(ring):
        if _on_segment(a, b, point):
            return True
        if (a.y > point.y) != (b.y > point.y):
            x = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < x:
                inside = not inside
    return inside


def _inside_fill(p: Point, contours: tuple[Ring, ...]) -> bool:
    # Even-odd parity supports holes and independent islands.
    return sum(_inside(p, contour) for contour in contours) % 2 == 1


def _sewable_connector(start: Point, end: Point,
                       contours: tuple[Ring, ...], max_mm: float = 8.0) -> bool:
    """Only stitch a turn if the entire quantised straight move stays in the fill.

    We partition the turn at every contour intersection. Testing the centre
    of each resulting interval avoids cutting across a hole or an L-shaped
    concavity. Fallback is always a needle-up jump.
    """
    ax, ay = quantise(start)
    bx, by = quantise(end)
    a = Point(ax / 10, ay / 10)
    b = Point(bx / 10, by / 10)
    dx, dy = b.x - a.x, b.y - a.y
    if hypot(dx, dy) > max_mm or not _inside_fill(a, contours) or not _inside_fill(b, contours):
        return False
    if (ax, ay) == (bx, by):
        return True
    split = [0.0, 1.0]
    for ring in contours:
        for c, d in _edges(ring):
            ex, ey = d.x - c.x, d.y - c.y
            denom = dx * ey - dy * ex
            if abs(denom) < 1e-12:
                continue
            qx, qy = c.x - a.x, c.y - a.y
            t = (qx * ey - qy * ex) / denom
            u = (qx * dy - qy * dx) / denom
            if -1e-10 <= t <= 1 + 1e-10 and -1e-10 <= u <= 1 + 1e-10:
                split.append(min(1.0, max(0.0, t)))
    split.sort()
    for lo, hi in zip(split, split[1:]):
        if hi - lo > 1e-9:
            mid = (lo + hi) / 2
            if not _inside_fill(Point(a.x + dx * mid, a.y + dy * mid), contours):
                return False
    return True


def validate_contours(contours: tuple[Ring, ...]) -> None:
    if not contours:
        raise ValueError("Tatami requires at least one closed contour")
    for index, ring in enumerate(contours):
        if len(ring) >= 2 and ring[-1] == ring[0]:
            raise ValueError("Remove repeated closing point from fill contour")
        if len(ring) < 3 or abs(_area(ring)) < 0.02:
            raise ValueError(f"Fill contour {index} has insufficient area")
        if any(hypot(a.x - b.x, a.y - b.y) < 1e-8 for a, b in _edges(ring)):
            raise ValueError(f"Fill contour {index} has duplicate adjacent points")
        edges = list(_edges(ring))
        for i, (a, b) in enumerate(edges):
            for j in range(i + 1, len(edges)):
                if j == i + 1 or i == 0 and j == len(edges) - 1:
                    continue
                if _intersect(a, b, edges[j][0], edges[j][1]):
                    raise ValueError(f"Fill contour {index} intersects itself")
    # Crossing/touching outlines are ambiguous with even-odd filling.
    for i, a in enumerate(contours):
        for b in contours[i + 1:]:
            if any(_intersect(p, q, r, s) for p, q in _edges(a)
                   for r, s in _edges(b)):
                raise ValueError("Fill contours cross or touch; separate the outlines")


def generate_tatami(contours: tuple[Ring, ...], source_sha256: str,
                    row_spacing_mm: float = 0.45, stitch_length_mm: float = 2.5,
                    angle_deg: float = 0.0) -> StitchPlan:
    if not isfinite(row_spacing_mm) or not 0.3 <= row_spacing_mm <= 3.0:
        raise ValueError("Tatami row spacing must be between 0.3 and 3 mm")
    if not isfinite(stitch_length_mm) or not 0.3 <= stitch_length_mm <= 8.0:
        raise ValueError("Tatami stitch length must be between 0.3 and 8 mm")
    if not isfinite(angle_deg) or abs(angle_deg) > 3600:
        raise ValueError("Tatami fill angle is invalid")
    validate_contours(contours)
    theta = radians(angle_deg)
    c, s = cos(theta), sin(theta)
    def rotate(p: Point) -> Point:
        return Point(p.x * c + p.y * s, -p.x * s + p.y * c)
    def back(x: float, y: float) -> Point:
        return Point(x * c - y * s, x * s + y * c)
    rotated = tuple(tuple(rotate(p) for p in ring) for ring in contours)
    all_y = [p.y for ring in rotated for p in ring]
    start, stop = min(all_y), max(all_y)
    count = floor((stop - start) / row_spacing_mm) + 1
    if count > 120_000:
        raise ValueError("Tatami row limit exceeded")
    builder = StitchBuilder(source_sha256, "tatami-evenodd-v1")
    for row in range(count):
        y = start + (row + .5) * row_spacing_mm
        if y >= stop:
            break
        crossings = []
        for ring in rotated:
            for a, b in _edges(ring):
                # Half-open interval removes double-counting at polygon vertices.
                if (a.y <= y < b.y) or (b.y <= y < a.y):
                    crossings.append(a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y))
        crossings.sort()
        if len(crossings) % 2:
            raise ValueError("Uneven tatami scanline intersections")
        segments = list(zip(crossings[::2], crossings[1::2]))
        # Alternate direction each row; no needle-down travel between intervals.
        if row % 2:
            segments.reverse()
        for lo, hi in segments:
            if hi - lo < 0.3:
                # This narrow component cannot take a safe stitch at these parameters.
                continue
            a, b = (lo, hi) if not row % 2 else (hi, lo)
            start_point = back(a, y)
            if builder.stitches and _sewable_connector(
                Point(builder.cursor[0] / 10, builder.cursor[1] / 10),
                start_point, contours):
                builder.sew(start_point)
            else:
                builder.travel(start_point)
            distance = abs(b - a)
            steps = max(1, ceil(distance / stitch_length_mm))
            for i in range(1, steps + 1):
                builder.sew(back(a + (b - a) * i / steps, y))
    return builder.finish()
