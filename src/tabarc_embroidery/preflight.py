"""Basic objective preflight. Passing here is NOT a real-machine safety guarantee."""
from __future__ import annotations
from dataclasses import dataclass
from math import hypot
from .model import Op, StitchPlan


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


def inspect_plan(plan: StitchPlan, hoop_width_mm: float, hoop_height_mm: float) -> list[Issue]:
    if hoop_width_mm <= 0 or hoop_height_mm <= 0:
        raise ValueError("Hoop dimensions must be positive")
    problems = []
    xs = [0] + [e.x10 for e in plan.events if e.opcode != Op.END]
    ys = [0] + [e.y10 for e in plan.events if e.opcode != Op.END]
    # This prototype places the source SVG's top-left corner at hoop origin.
    # Check occupied size, then separate negative coordinates/out-of-bounds.
    if min(xs) < 0 or min(ys) < 0 or max(xs) > hoop_width_mm * 10 or max(ys) > hoop_height_mm * 10:
        problems.append(Issue("ERROR", "OUTSIDE_HOOP",
                              "Stitch positions fall outside the top-left anchored hoop"))
    prev = (0, 0)
    stitches = 0
    for i, e in enumerate(plan.events):
        if e.opcode == Op.END:
            break
        dx = (e.x10 - prev[0]) / 10
        dy = (e.y10 - prev[1]) / 10
        size = hypot(dx, dy)
        if e.opcode == Op.STITCH:
            stitches += 1
            if size < 0.3:
                problems.append(Issue("WARNING", "SHORT_STITCH", f"Stitch {i}: {size:.2f} mm"))
            if size > 8.1:
                problems.append(Issue("ERROR", "LONG_STITCH", f"Stitch {i}: {size:.2f} mm"))
        if abs(dx) > 12.1 or abs(dy) > 12.1:
            problems.append(Issue("ERROR", "UNREPRESENTABLE_DST", f"Record {i}"))
        prev = (e.x10, e.y10)
    if not stitches:
        problems.append(Issue("ERROR", "EMPTY_STITCH_PLAN", "No actual needle-down stitches"))
    return problems
