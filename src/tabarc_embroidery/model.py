"""Immutable canonical-mm geometry and DST-precision stitch events."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise ValueError("Point coordinates must be finite")


@dataclass(frozen=True)
class Stroke:
    name: str
    points: tuple[Point, ...]
    closed: bool = False


@dataclass(frozen=True)
class StitchSettings:
    style: str = "running"
    stitch_length_mm: float = 2.5
    row_spacing_mm: float = 0.45
    angle_deg: float = 0.0
    satin_spacing_mm: float = 0.4
    max_satin_width_mm: float = 8.0

    def __post_init__(self) -> None:
        if self.style not in ("running", "satin", "tatami"):
            raise ValueError(f"Unknown stitch style: {self.style}")
        for name in ("stitch_length_mm", "row_spacing_mm", "angle_deg",
                     "satin_spacing_mm", "max_satin_width_mm"):
            if not isfinite(getattr(self, name)):
                raise ValueError(f"Non-finite stitch parameter: {name}")


@dataclass(frozen=True)
class Document:
    width_mm: float
    height_mm: float
    strokes: tuple[Stroke, ...]
    source_sha256: str
    settings: StitchSettings = field(default_factory=StitchSettings)

    def __post_init__(self) -> None:
        if not (isfinite(self.width_mm) and isfinite(self.height_mm)):
            raise ValueError("Document dimensions must be finite")
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError("Document dimensions must be positive")


class Op(str, Enum):
    STITCH = "STITCH"
    JUMP = "JUMP"
    COLOUR_CHANGE = "COLOUR_CHANGE"
    TRIM = "TRIM"
    STOP = "STOP"
    END = "END"


@dataclass(frozen=True)
class Event:
    opcode: Op
    x10: int  # 0.1 mm integer DST grid
    y10: int

    @property
    def point_mm(self) -> Point:
        return Point(self.x10 / 10, self.y10 / 10)


@dataclass(frozen=True)
class StitchPlan:
    events: tuple[Event, ...]
    source_sha256: str
    generator_version: str = "run-v1"
    thread_palette: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.events or self.events[-1].opcode != Op.END:
            raise ValueError("Stitch plan must finish with END")
        if any(e.opcode == Op.END for e in self.events[:-1]):
            raise ValueError("END must be the final event")
