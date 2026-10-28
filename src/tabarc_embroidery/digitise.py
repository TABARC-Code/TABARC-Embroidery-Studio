"""Translate explicit document stitch settings into a common needle plan."""
from __future__ import annotations

from .model import Document, StitchPlan
from .running import generate_running
from .satin import generate_satin
from .tatami import generate_tatami


def generate_plan(document: Document) -> StitchPlan:
    s = document.settings
    if s.style == "running":
        return generate_running(document, stitch_length_mm=s.stitch_length_mm)
    if s.style == "satin":
        if len(document.strokes) != 2 or any(st.closed for st in document.strokes):
            raise ValueError("Satin needs exactly two open SVG paths, in rail order")
        return generate_satin(document.strokes[0].points, document.strokes[1].points,
                              document.source_sha256, s.satin_spacing_mm,
                              s.max_satin_width_mm)
    if s.style == "tatami":
        if not document.strokes or any(not st.closed for st in document.strokes):
            raise ValueError("Tatami needs closed polygon contours only")
        return generate_tatami(tuple(st.points for st in document.strokes),
                               document.source_sha256, s.row_spacing_mm,
                               s.stitch_length_mm, s.angle_deg)
    raise ValueError(f"Unknown stitch style {s.style!r}")
