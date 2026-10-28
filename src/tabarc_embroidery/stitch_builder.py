"""Small, bounded collector for fixed-grid needle instructions.

Travel never becomes a needle-down stitch. No implicit trims are attempted.
"""
from __future__ import annotations

from math import ceil, hypot

from .model import Event, Op, Point, StitchPlan

MAX_EVENTS = 250_000


def quantise(point: Point) -> tuple[int, int]:
    return round(point.x * 10), round(point.y * 10)


class StitchBuilder:
    def __init__(self, source_sha256: str, generator_version: str):
        self.source_sha256 = source_sha256
        self.generator_version = generator_version
        self.events: list[Event] = []
        self.cursor = (0, 0)
        self.stitches = 0

    def _append(self, kind: Op, target: tuple[int, int]) -> None:
        if len(self.events) >= MAX_EVENTS:
            raise ValueError("Needle event limit exceeded")
        if max(abs(target[0] - self.cursor[0]), abs(target[1] - self.cursor[1])) > 121:
            raise ValueError("DST movement exceeds representable distance")
        if target == self.cursor:
            return
        self.events.append(Event(kind, *target))
        self.cursor = target
        if kind == Op.STITCH:
            self.stitches += 1

    def travel(self, target: Point) -> None:
        goal = quantise(target)
        origin = self.cursor
        dx, dy = goal[0] - origin[0], goal[1] - origin[1]
        count = ceil(max(abs(dx), abs(dy)) / 121)
        for i in range(1, count + 1):
            self._append(Op.JUMP, (origin[0] + round(dx * i / count),
                                   origin[1] + round(dy * i / count)))

    def sew(self, target: Point, max_stitch_mm: float = 8.0) -> None:
        goal = quantise(target)
        origin = self.cursor
        dx, dy = goal[0] - origin[0], goal[1] - origin[1]
        length = hypot(dx, dy) / 10
        count = max(1, ceil(length / max_stitch_mm))
        for i in range(1, count + 1):
            self._append(Op.STITCH, (origin[0] + round(dx * i / count),
                                     origin[1] + round(dy * i / count)))

    def finish(self) -> StitchPlan:
        if self.stitches == 0:
            raise ValueError("No needle-down stitches generated")
        return StitchPlan(tuple(self.events + [Event(Op.END, *self.cursor)]),
                          self.source_sha256, self.generator_version)
