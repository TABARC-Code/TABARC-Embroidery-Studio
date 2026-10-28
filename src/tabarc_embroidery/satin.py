"""Explicit two-rail satin prototype. No automatic stroke-to-satin inference.

Rails are sampled by normalised arclength; the chosen correspondence is a
geometric approximation and requires visual checking on curved columns.
"""
from __future__ import annotations

from math import ceil, hypot, isfinite

from .model import Point, StitchPlan
from .stitch_builder import StitchBuilder


def _distance(a: Point, b: Point) -> float:
    return hypot(b.x - a.x, b.y - a.y)


def _length(rail: tuple[Point, ...]) -> float:
    return sum(_distance(a, b) for a, b in zip(rail, rail[1:]))


def _at(rail: tuple[Point, ...], fraction: float) -> Point:
    total = _length(rail)
    distance = fraction * total
    for a, b in zip(rail, rail[1:]):
        segment = _distance(a, b)
        if distance <= segment:
            t = min(1, distance / segment)
            return Point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
        distance -= segment
    return rail[-1]


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _proper_intersection(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Detect strict segment crossings; shared-endpoint/tangent is checked by widths."""
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return o1 * o2 < -1e-9 and o3 * o4 < -1e-9


def generate_satin(left: tuple[Point, ...], right: tuple[Point, ...],
                   source_sha256: str, spacing_mm: float = 0.4,
                   max_width_mm: float = 8.0) -> StitchPlan:
    if not isfinite(spacing_mm) or not 0.3 <= spacing_mm <= 2.0:
        raise ValueError("Satin spacing must be between 0.3 and 2 mm")
    if not isfinite(max_width_mm) or not 0.5 <= max_width_mm <= 12.1:
        raise ValueError("Satin width limit must be between 0.5 and 12.1 mm")
    if len(left) < 2 or len(right) < 2:
        raise ValueError("Satin requires two rails with at least two points each")
    if any(_distance(a, b) < 1e-8 for rail in (left, right)
           for a, b in zip(rail, rail[1:])):
        raise ValueError("Satin rails contain zero-length segments")
    for a, b in zip(left, left[1:]):
        for c, d in zip(right, right[1:]):
            if _proper_intersection(a, b, c, d):
                raise ValueError("Satin rails cross; fix the source geometry")
    length = max(_length(left), _length(right))
    if length < spacing_mm:
        raise ValueError("Satin column is shorter than its stitch spacing")
    samples = ceil(length / spacing_mm)
    if samples * 2 > 250_000:
        raise ValueError("Satin sample limit exceeded")
    builder = StitchBuilder(source_sha256, "satin-rails-v1")
    # First rail to second rail, then move to the next point on the first.
    # A jump to the first needle point avoids sewing from document origin.
    builder.travel(left[0])
    for index in range(samples + 1):
        t = index / samples
        a, b = _at(left, t), _at(right, t)
        width = _distance(a, b)
        if width < 0.3:
            raise ValueError(f"Satin column collapses below 0.3 mm at {t:.2f}")
        if width > max_width_mm + 1e-8:
            raise ValueError(f"Satin width {width:.2f} mm exceeds {max_width_mm:g} mm")
        if index:
            builder.sew(a)
        builder.sew(b)
    return builder.finish()
