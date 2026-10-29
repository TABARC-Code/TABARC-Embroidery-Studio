"""Conservative, object-level warnings. These aren't a substitute for sew-outs.

Checks use saved geometry and explicit settings rather than guessing a fabric,
needle or thread. Never label a mathematically valid file 'machine-safe'.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from .design import DesignDocument


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    object_id: str
    message: str


def inspect_design(design: DesignDocument) -> list[Diagnostic]:
    """List bounded, deterministic warnings for editable sewing objects."""
    issues: list[Diagnostic] = []
    for obj in design.objects:
        if not obj.visible:
            continue

        def add(severity: str, code: str, message: str) -> None:
            issues.append(Diagnostic(severity, code, obj.object_id, message))

        if obj.kind == 'reference':
            add('INFO', 'REFERENCE_NOT_SEWN', 'Reference artwork is not exported as stitches')
            continue
        if obj.kind in {'stop', 'trim'}:
            add('ERROR', 'UNSUPPORTED_DST_CONTROL',
                f'{obj.kind.upper()} cannot be exported by the built-in DST writer')
            continue
        if obj.kind not in {'running', 'satin', 'tatami'}:
            continue
        for contour_index, contour in enumerate(obj.strokes):
            if not contour.points:
                add('ERROR', 'EMPTY_CONTOUR', f'Contour {contour_index + 1} has no geometry')
                continue
            if any(p.x < 0 or p.y < 0 or p.x > design.width_mm or
                   p.y > design.height_mm for p in contour.points):
                add('ERROR', 'GEOMETRY_OUTSIDE_HOOP',
                    f'Contour {contour_index + 1} extends outside the hoop')
            edges = zip(contour.points, contour.points[1:] +
                        (contour.points[:1] if contour.closed else ()))
            short = sum(0 < hypot(a.x - b.x, a.y - b.y) < 0.3 for a, b in edges)
            if short:
                add('WARNING', 'SHORT_SOURCE_EDGES',
                    f'Contour {contour_index + 1}: {short} source edges shorter than 0.3 mm')
            if obj.kind == 'tatami':
                xs = [p.x for p in contour.points]
                ys = [p.y for p in contour.points]
                if min(max(xs) - min(xs), max(ys) - min(ys)) < 1.0:
                    add('WARNING', 'NARROW_CONTOUR_BOUNDS',
                        f'Contour {contour_index + 1} has a bounding dimension below 1 mm')
        settings = obj.settings
        if obj.kind == 'tatami' and settings.row_spacing_mm < 0.30:
            add('WARNING', 'CLOSE_FILL_ROWS',
                f'Fill rows are {settings.row_spacing_mm:g} mm apart; check density on fabric')
        if obj.kind == 'satin' and settings.max_satin_width_mm > 10.0:
            add('WARNING', 'WIDE_SATIN_LIMIT',
                f'Satin limit is {settings.max_satin_width_mm:g} mm; wide spans may snag')
        if obj.kind == 'running' and settings.stitch_length_mm > 6.0:
            add('WARNING', 'LONG_RUNNING_SETTING',
                f'Running stitch target is {settings.stitch_length_mm:g} mm')
    return issues
