"""Editable multi-object document; machine instructions remain a separate product.

Original cubic control points are preserved as reference geometry, not inferred
stitches. Object ordering is sewing order, not automatic route optimisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import ceil, hypot, isfinite
from typing import Any
import json

from .digitise import generate_plan
from .model import Document, Event, Op, Point, StitchPlan, StitchSettings, Stroke
from .stitch_builder import MAX_EVENTS

STITCH_KINDS = frozenset({'running', 'satin', 'tatami'})
CONTROL_KINDS = frozenset({'trim', 'stop', 'colour_change'})
OBJECT_KINDS = STITCH_KINDS | CONTROL_KINDS | {'reference'}


def validate_thread(value: str) -> str:
    if not isinstance(value, str) or len(value) != 7 or value[0] != '#' or any(
        letter not in '0123456789abcdefABCDEF' for letter in value[1:]
    ):
        raise ValueError('Thread colour must be six-digit hex: #RRGGBB')
    return value.upper()


@dataclass(frozen=True)
class CubicSegment:
    p0: Point
    p1: Point
    p2: Point
    p3: Point


@dataclass(frozen=True)
class CurvePath:
    segments: tuple[CubicSegment, ...]
    closed: bool = False


@dataclass(frozen=True)
class EmbroideryObject:
    object_id: str
    name: str
    kind: str
    strokes: tuple[Stroke, ...] = ()
    settings: StitchSettings = field(default_factory=StitchSettings)
    thread_hex: str = '#000000'
    visible: bool = True
    curve_paths: tuple[CurvePath, ...] = ()
    original_style: str | None = None
    original_parameters: dict[str, Any] = field(default_factory=dict)
    unrendered_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, str) or not (1 <= len(self.object_id) <= 128):
            raise ValueError('Object ID must be a nonempty string of at most 128 characters')
        if not isinstance(self.name, str) or len(self.name) > 512:
            raise ValueError('Invalid object name')
        if self.kind not in OBJECT_KINDS:
            raise ValueError(f'Unsupported object kind: {self.kind}')
        if type(self.visible) is not bool:
            raise ValueError('visible must be boolean')
        if self.kind in CONTROL_KINDS and (self.strokes or self.curve_paths):
            raise ValueError('Control objects cannot carry geometry')
        if self.kind in STITCH_KINDS and not self.strokes:
            raise ValueError(f'{self.kind} needs flattened geometry; native curves are reference-only')
        if self.kind in STITCH_KINDS and self.settings.style != self.kind:
            raise ValueError('Per-object stitch settings must match the object kind')
        if len(self.strokes) > 10000 or len(self.curve_paths) > 10000:
            raise ValueError('Too many object paths')
        validate_thread(self.thread_hex)
        try:
            json.dumps(self.original_parameters, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('Native parameters must be finite JSON') from exc


@dataclass(frozen=True)
class DesignDocument:
    width_mm: float
    height_mm: float
    objects: tuple[EmbroideryObject, ...]
    source_sha256: str
    source_format: str = 'svg'  # the preserved source asset format

    def __post_init__(self) -> None:
        if not all(isfinite(v) and 0 < v <= 10000 for v in (self.width_mm, self.height_mm)):
            raise ValueError('Invalid design dimensions')
        if self.source_format not in {'svg', 'ostch'}:
            raise ValueError('Unknown source asset format')
        if len(self.objects) > 10000:
            raise ValueError('Object limit exceeded')
        ids = [obj.object_id for obj in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate design object IDs')
        if (len(self.source_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.source_sha256)):
            raise ValueError('Invalid source SHA-256')


def design_from_svg(source: bytes, assignments: dict[str, Any], *, tolerance_mm: float = 0.06) -> DesignDocument:
    """Assign imported SVG strokes to independently digitised objects.

    Every path must be assigned once or more explicitly; no silent omissions.
    Uses the v0.5 SVG importer and its existing unsupported-SVG safeguards.
    """
    from .svg_import import import_svg
    if not isinstance(assignments, dict) or set(assignments) != {'objects'}:
        raise ValueError('Assignments must be an object containing only an objects array')
    raw_objects = assignments['objects']
    if not isinstance(raw_objects, list) or not (1 <= len(raw_objects) <= 1000):
        raise ValueError('Assignments require 1–1000 objects')
    imported = import_svg(source, tolerance_mm=tolerance_mm)
    objects = []
    used: set[int] = set()
    for record in raw_objects:
        if not isinstance(record, dict):
            raise ValueError('Each assignment must be an object')
        extra = set(record) - {'id', 'name', 'kind', 'stroke_indices', 'settings', 'thread_hex', 'visible'}
        if extra:
            raise ValueError(f'Unknown assignment fields: {sorted(extra)}')
        kind = record.get('kind', 'running')
        indices = record.get('stroke_indices', [])
        if not isinstance(indices, list) or any(type(i) is not int or not 0 <= i < len(imported.strokes) for i in indices):
            raise ValueError('stroke_indices must refer to imported SVG paths')
        if len(set(indices)) != len(indices):
            raise ValueError('Duplicate path indices inside an object')
        used.update(indices)
        config = record.get('settings', {})
        if not isinstance(config, dict):
            raise ValueError('settings must be an object')
        settings = StitchSettings(**{'style': kind if kind in STITCH_KINDS else 'running', **config})
        objects.append(EmbroideryObject(
            str(record['id']), str(record.get('name', record['id'])), str(kind),
            tuple(imported.strokes[i] for i in indices), settings,
            validate_thread(record.get('thread_hex', '#000000')),
            record.get('visible', True),
        ))
    if used != set(range(len(imported.strokes))):
        raise ValueError(f'Unassigned SVG paths: {sorted(set(range(len(imported.strokes))) - used)}')
    return DesignDocument(imported.width_mm, imported.height_mm, tuple(objects), imported.source_sha256)


def design_from_native(native: Any) -> DesignDocument:
    """Preserve observed native curves and metadata as non-sewing reference objects.

    No source stitch style is automatically translated to a TABARC sewing style.
    """
    objects = []
    for obj in native.objects:
        paths = tuple(CurvePath(tuple(CubicSegment(*(Point(*p) for p in (
            seg.p0, seg.p1, seg.p2, seg.p3))) for seg in path.segments), path.closed)
            for path in obj.paths)
        objects.append(EmbroideryObject(
            str(obj.object_id), obj.name, 'reference', (), StitchSettings(),
            '#%02X%02X%02X' % obj.colour, obj.visible, paths,
            obj.style, obj.style_parameters, obj.unrendered_features,
        ))
    hoop = native.hoop or {}
    coords = [p for obj in native.objects for path in obj.paths for seg in path.segments
              for p in (seg.p0, seg.p1, seg.p2, seg.p3)]
    max_x = max((p[0] for p in coords), default=0)
    max_y = max((p[1] for p in coords), default=0)
    def dimension(key: str, estimate: float) -> float:
        v = hoop.get(key)
        return float(v) if type(v) in (int, float) and isfinite(v) and 0 < v <= 10000 else max(1., estimate + 5.)
    return DesignDocument(dimension('width_mm', max_x), dimension('height_mm', max_y),
                          tuple(objects), native.source_sha256, 'ostch')


def _jump_from(cursor: tuple[int, int], goal: tuple[int, int]) -> list[Event]:
    dx, dy = goal[0] - cursor[0], goal[1] - cursor[1]
    steps = ceil(max(abs(dx), abs(dy)) / 121)
    return [Event(Op.JUMP, cursor[0] + round(dx * i / steps),
                  cursor[1] + round(dy * i / steps)) for i in range(1, steps + 1)]


def generate_design_plan(design: DesignDocument) -> StitchPlan:
    """Compose per-object needle events with explicit stitch/jump/control semantics."""
    events: list[Event] = []
    palette: list[str] = []
    cursor = (0, 0)
    current_colour: str | None = None
    stitched = False

    def add(event: Event) -> None:
        nonlocal cursor
        if len(events) >= MAX_EVENTS:
            raise ValueError('Combined design event limit exceeded')
        if max(abs(event.x10 - cursor[0]), abs(event.y10 - cursor[1])) > 121:
            raise ValueError('Combined event exceeds DST coordinate step')
        if event.opcode in {Op.COLOUR_CHANGE, Op.STOP, Op.TRIM} and (event.x10, event.y10) != cursor:
            raise ValueError('Control operation must not move needle')
        events.append(event)
        cursor = event.x10, event.y10

    for obj in design.objects:
        if not obj.visible or obj.kind == 'reference':
            continue
        if obj.kind in CONTROL_KINDS:
            if not stitched:
                raise ValueError(f'Control {obj.kind} requires preceding stitches')
            if obj.kind == 'colour_change':
                add(Event(Op.COLOUR_CHANGE, *cursor))
                current_colour = validate_thread(obj.thread_hex)
                palette.append(current_colour)
            elif obj.kind == 'trim':
                add(Event(Op.TRIM, *cursor))
            else:
                add(Event(Op.STOP, *cursor))
            continue
        subdoc = Document(design.width_mm, design.height_mm, obj.strokes,
                          design.source_sha256, obj.settings)
        part = generate_plan(subdoc)
        first_sew = next((i for i, ev in enumerate(part.events) if ev.opcode == Op.STITCH), None)
        if first_sew is None:
            raise ValueError(f'Object {obj.object_id} produced no stitches')
        # All existing generators use initial jumps only to reach the first
        # sewing start from (0,0). Replace them with jumps from our live cursor.
        leading = part.events[:first_sew]
        if any(e.opcode != Op.JUMP for e in leading):
            raise ValueError('Unexpected machine command in object lead-in')
        anchor = (leading[-1].x10, leading[-1].y10) if leading else (0, 0)
        if current_colour is None:
            current_colour = validate_thread(obj.thread_hex)
            palette.append(current_colour)
        elif current_colour != validate_thread(obj.thread_hex):
            add(Event(Op.COLOUR_CHANGE, *cursor))
            current_colour = validate_thread(obj.thread_hex)
            palette.append(current_colour)
        for jump in _jump_from(cursor, anchor):
            add(jump)
        for ev in part.events[first_sew:-1]:
            add(ev)
        stitched = True
    if not stitched:
        raise ValueError('Design contains no stitchable visible objects')
    add(Event(Op.END, *cursor))
    return StitchPlan(tuple(events), design.source_sha256, 'multi-object-v1', tuple(palette))


def promote_reference_running(design: DesignDocument, object_id: str, *,
                              tolerance_mm: float = 0.06) -> DesignDocument:
    """Opt-in approximation for one *observed* native Running object only.

    The original cubic paths and parameters are retained. The generated
    polylines describe geometric sampling, not native stitch fidelity.
    """
    from .svg_import import Matrix, _cubic
    if not isfinite(tolerance_mm) or not 0.01 <= tolerance_mm <= 0.5:
        raise ValueError('Curve tolerance must be 0.01–0.5 mm')
    selected = next((o for o in design.objects if o.object_id == object_id), None)
    if selected is None:
        raise ValueError(f'Unknown object ID: {object_id}')
    if selected.kind != 'reference' or selected.original_style != 'Running':
        raise ValueError('Only native Running reference objects may be promoted')
    if selected.unrendered_features:
        raise ValueError('Native object has unrendered features; refusing promotion')
    params = selected.original_parameters
    if set(params) - {'spacing_mm'}:
        raise ValueError('Unknown native Running settings; refusing promotion')
    spacing = params.get('spacing_mm', 2.5)
    if type(spacing) not in (int, float):
        raise ValueError('Native Running spacing must be numeric')
    settings = StitchSettings(style='running', stitch_length_mm=float(spacing))
    strokes = []
    for path_index, path in enumerate(selected.curve_paths):
        points: list[Point] = []
        for seg in path.segments:
            if points and hypot(points[-1].x - seg.p0.x, points[-1].y - seg.p0.y) > 1e-5:
                if len(points) >= 2:
                    strokes.append(Stroke(f'{object_id}:{path_index}:{len(strokes)}',
                                          tuple(points)))
                points = []
            if not points:
                points.append(seg.p0)
            points.extend(_cubic(seg.p0, seg.p1, seg.p2, seg.p3,
                                 Matrix(), tolerance_mm))
        if len(points) >= 2:
            if path.closed and points[-1] == points[0]:
                points.pop()
            strokes.append(Stroke(f'{object_id}:{path_index}', tuple(points), path.closed))
    if not strokes:
        raise ValueError('Native reference lacks usable cubic geometry')
    promoted = replace(selected, kind='running', strokes=tuple(strokes), settings=settings)
    return replace(design, objects=tuple(promoted if o.object_id == object_id else o
                                        for o in design.objects))
