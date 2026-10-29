"""Headless document editing for the desktop workspace.

The original artwork remains untouched in the project archive. Changing a shape
updates the editable geometry, not the source checksum. Undo is cheap enough for
now; large documents will want a command log rather than whole snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import copysign, floor, isfinite
from typing import Sequence

from .design import (CubicSegment, CurvePath, DesignDocument, EmbroideryObject,
                     validate_thread)
from .model import Document, Point, StitchSettings, Stroke

MAX_UNDO = 60
MAX_DRAW_POINTS = 5000


def snap_coordinate(value_mm: float, grid_mm: float) -> float:
    """Round to the nearest mm grid, including halfway values away from zero."""
    if not isfinite(value_mm) or abs(value_mm) > 100000:
        raise ValueError("Snap position is outside supported coordinates")
    if not isfinite(grid_mm) or not 0.1 <= grid_mm <= 100:
        raise ValueError("Grid spacing must be between 0.1 and 100 mm")
    steps = floor(abs(value_mm) / grid_mm + 0.5)
    return round(copysign(steps * grid_mm, value_mm), 8)



def as_design(document: Document | DesignDocument) -> DesignDocument:
    """Upgrade a legacy single-style project without altering its source bytes."""
    if isinstance(document, DesignDocument):
        return document
    return DesignDocument(
        document.width_mm, document.height_mm,
        (EmbroideryObject('artwork', 'Artwork', document.settings.style,
                          document.strokes, document.settings),),
        document.source_sha256,
    )


def translate_object(obj: EmbroideryObject, dx_mm: float, dy_mm: float) -> EmbroideryObject:
    if not all(isfinite(v) and abs(v) <= 10000 for v in (dx_mm, dy_mm)):
        raise ValueError('Movement must be finite and within 10,000 mm')

    def shift(p: Point) -> Point:
        x, y = p.x + dx_mm, p.y + dy_mm
        if not all(isfinite(n) and abs(n) <= 100000 for n in (x, y)):
            raise ValueError('Moved geometry exceeds supported coordinates')
        return Point(x, y)

    strokes = tuple(Stroke(s.name, tuple(shift(p) for p in s.points), s.closed)
                    for s in obj.strokes)
    curves = tuple(CurvePath(tuple(CubicSegment(*(shift(p) for p in
                      (seg.p0, seg.p1, seg.p2, seg.p3))) for seg in path.segments),
                      path.closed) for path in obj.curve_paths)
    return replace(obj, strokes=strokes, curve_paths=curves)


@dataclass
class EditorSession:
    design: DesignDocument
    source: bytes

    def __post_init__(self) -> None:
        from hashlib import sha256
        if sha256(self.source).hexdigest() != self.design.source_sha256:
            raise ValueError('Document and source artwork do not match')
        self._undo: list[DesignDocument] = []
        self._redo: list[DesignDocument] = []
        self._saved: DesignDocument = self.design
        self.revision = 0

    @property
    def dirty(self) -> bool:
        return self.design != self._saved

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def mark_saved(self) -> None:
        self._saved = self.design

    def mark_unsaved(self) -> None:
        """Newly imported artwork has never been written to a project file."""
        self._saved = None

    def _apply(self, updated: DesignDocument) -> None:
        if updated == self.design:
            return
        self._undo.append(self.design)
        del self._undo[:-MAX_UNDO]
        self._redo.clear()
        self.design = updated
        self.revision += 1

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.design)
        self.design = self._undo.pop()
        self.revision += 1
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.design)
        self.design = self._redo.pop()
        self.revision += 1
        return True

    def object(self, object_id: str) -> EmbroideryObject:
        for obj in self.design.objects:
            if obj.object_id == object_id:
                return obj
        raise ValueError(f'Unknown object: {object_id}')

    def change(self, object_id: str, *, name: str | None = None,
               thread_hex: str | None = None, visible: bool | None = None,
               settings: StitchSettings | None = None) -> None:
        original = self.object(object_id)
        if visible is not None and type(visible) is not bool:
            raise ValueError('Visibility must be boolean')
        if settings is not None and original.kind in {'running', 'satin', 'tatami'}:
            if settings.style != original.kind:
                raise ValueError('Stitch settings must match the existing object kind')
        if settings is not None and not isinstance(settings, StitchSettings):
            raise ValueError('Invalid stitch settings')
        updated = replace(original,
                          name=original.name if name is None else name,
                          thread_hex=original.thread_hex if thread_hex is None
                          else validate_thread(thread_hex),
                          visible=original.visible if visible is None else visible,
                          settings=original.settings if settings is None else settings)
        self._replace(object_id, updated)

    def move(self, object_id: str, dx_mm: float, dy_mm: float,
             *, grid_mm: float | None = None) -> None:
        obj = self.object(object_id)
        if not all(isfinite(v) and abs(v) <= 10000 for v in (dx_mm, dy_mm)):
            raise ValueError('Movement must be finite and within 10,000 mm')
        if grid_mm is not None:
            if obj.strokes and obj.strokes[0].points:
                anchor = obj.strokes[0].points[0]
            elif obj.curve_paths and obj.curve_paths[0].segments:
                anchor = obj.curve_paths[0].segments[0].p0
            else:
                raise ValueError('Cannot snap an object without geometry')
            dx_mm = snap_coordinate(anchor.x + dx_mm, grid_mm) - anchor.x
            dy_mm = snap_coordinate(anchor.y + dy_mm, grid_mm) - anchor.y
        self._replace(object_id, translate_object(obj, dx_mm, dy_mm))

    def add_running_path(self, points: Sequence[Point], *, name: str = 'Running path',
                         thread_hex: str = '#000000') -> str:
        """Add an editable open polyline. Never alter the original imported artwork."""
        if len(self.design.objects) >= 10000:
            raise ValueError('Object limit reached')
        if not isinstance(name, str) or not name or len(name) > 512:
            raise ValueError('Path needs a name (maximum 512 characters)')
        points = tuple(points)
        if not 2 <= len(points) <= MAX_DRAW_POINTS or any(not isinstance(p, Point) for p in points):
            raise ValueError('Running path requires 2–5000 finite points')
        if any(abs(p.x) > 10000 or abs(p.y) > 10000 for p in points):
            raise ValueError('Drawn path exceeds supported coordinates')
        if any(a == b for a, b in zip(points, points[1:])) or len(set(points)) < 2:
            raise ValueError('Running path contains duplicate neighbouring points')
        thread_hex = validate_thread(thread_hex)
        taken = {obj.object_id for obj in self.design.objects}
        counter = 1
        while f'drawn-{counter}' in taken:
            counter += 1
        ident = f'drawn-{counter}'
        obj = EmbroideryObject(ident, name, 'running',
                              (Stroke(ident, points),), StitchSettings(style='running'),
                              thread_hex)
        self._apply(replace(self.design, objects=self.design.objects + (obj,)))
        return ident

    def _replace_stroke(self, object_id: str, stroke_index: int, stroke: Stroke) -> None:
        obj = self.object(object_id)
        if obj.kind not in {'running', 'tatami'} or obj.curve_paths:
            raise ValueError('Only flattened running and tatami paths are node-editable')
        if type(stroke_index) is not int or not 0 <= stroke_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        if not 2 <= len(stroke.points) <= MAX_DRAW_POINTS:
            raise ValueError('Contour requires 2–5000 vertices')
        if stroke.closed and len(stroke.points) < 3:
            raise ValueError('A closed contour needs at least three vertices')
        if obj.kind == 'tatami' and not stroke.closed:
            raise ValueError('Tatami contours must remain closed')
        if any(not isinstance(p, Point) or abs(p.x) > 10000 or abs(p.y) > 10000
               for p in stroke.points):
            raise ValueError('Contour coordinates exceed supported limits')
        if any(a == b for a, b in zip(stroke.points, stroke.points[1:])):
            raise ValueError('Duplicate neighbouring vertices')
        strokes = list(obj.strokes)
        strokes[stroke_index] = stroke
        if obj.kind == 'tatami':
            from .tatami import validate_contours
            validate_contours(tuple(s.points for s in strokes))
        self._replace(object_id, replace(obj, strokes=tuple(strokes)))

    def edit_node(self, object_id: str, stroke_index: int, node_index: int,
                  point: Point, *, grid_mm: float | None = None) -> None:
        obj = self.object(object_id)
        if type(stroke_index) is not int or not 0 <= stroke_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        stroke = obj.strokes[stroke_index]
        if type(node_index) is not int or not 0 <= node_index < len(stroke.points):
            raise ValueError('Invalid vertex index')
        if not isinstance(point, Point):
            raise ValueError('Vertex must be a point')
        if grid_mm is not None:
            point = Point(snap_coordinate(point.x, grid_mm), snap_coordinate(point.y, grid_mm))
        points = list(stroke.points)
        points[node_index] = point
        self._replace_stroke(object_id, stroke_index, replace(stroke, points=tuple(points)))

    def insert_node(self, object_id: str, stroke_index: int, after_index: int) -> None:
        obj = self.object(object_id)
        if type(stroke_index) is not int or not 0 <= stroke_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        stroke = obj.strokes[stroke_index]
        if type(after_index) is not int or not 0 <= after_index < len(stroke.points):
            raise ValueError('Invalid vertex index')
        if after_index == len(stroke.points) - 1 and not stroke.closed:
            raise ValueError('The last vertex has no next segment')
        a, b = stroke.points[after_index], stroke.points[(after_index + 1) % len(stroke.points)]
        points = list(stroke.points)
        points.insert(after_index + 1, Point((a.x + b.x) / 2, (a.y + b.y) / 2))
        self._replace_stroke(object_id, stroke_index, replace(stroke, points=tuple(points)))

    def delete_node(self, object_id: str, stroke_index: int, node_index: int) -> None:
        obj = self.object(object_id)
        if type(stroke_index) is not int or not 0 <= stroke_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        stroke = obj.strokes[stroke_index]
        if type(node_index) is not int or not 0 <= node_index < len(stroke.points):
            raise ValueError('Invalid vertex index')
        points = list(stroke.points)
        points.pop(node_index)
        self._replace_stroke(object_id, stroke_index, replace(stroke, points=tuple(points)))

    def close_contour(self, object_id: str, stroke_index: int = 0,
                      *, closed: bool = True) -> None:
        obj = self.object(object_id)
        if type(stroke_index) is not int or not 0 <= stroke_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        stroke = obj.strokes[stroke_index]
        if type(closed) is not bool:
            raise ValueError('Closed must be boolean')
        self._replace_stroke(object_id, stroke_index, replace(stroke, closed=closed))

    def group_fill_contours(self, object_ids: Sequence[str], *, name: str = 'Compound fill') -> str:
        """Combine closed paths, retaining their separate rings for even-odd holes."""
        object_ids = tuple(object_ids)
        if len(object_ids) < 2 or len(object_ids) != len(set(object_ids)):
            raise ValueError('Select at least two distinct contour objects')
        if not isinstance(name, str) or not name or len(name) > 512:
            raise ValueError('Invalid compound fill name')
        sources = [self.object(oid) for oid in object_ids]
        if any(obj.kind not in {'running', 'tatami'} or obj.curve_paths or
               not obj.strokes or any(not s.closed for s in obj.strokes) for obj in sources):
            raise ValueError('Only closed, flattened running/tatami contours can be grouped')
        if any(obj.thread_hex != sources[0].thread_hex for obj in sources):
            raise ValueError('Grouped fill contours must share one thread colour')
        if any(obj.visible != sources[0].visible for obj in sources):
            raise ValueError('Grouped contours must have the same visibility')
        strokes = tuple(stroke for obj in sources for stroke in obj.strokes)
        from .tatami import validate_contours
        validate_contours(tuple(stroke.points for stroke in strokes))
        ids = {obj.object_id for obj in self.design.objects}
        number = 1
        while f'fill-{number}' in ids:
            number += 1
        ident = f'fill-{number}'
        settings = (sources[0].settings if sources[0].kind == 'tatami'
                    else StitchSettings(style='tatami'))
        merged = EmbroideryObject(ident, name, 'tatami', strokes, settings,
                                  sources[0].thread_hex, sources[0].visible)
        selection = set(object_ids)
        first_index = min(i for i, obj in enumerate(self.design.objects)
                          if obj.object_id in selection)
        remainder = [o for o in self.design.objects if o.object_id not in selection]
        remainder.insert(first_index, merged)
        self._apply(replace(self.design, objects=tuple(remainder)))
        return ident

    def remove_contour(self, object_id: str, contour_index: int) -> None:
        """Remove one ring from a multi-contour fill in a single undo step."""
        obj = self.object(object_id)
        if obj.kind != 'tatami' or obj.curve_paths or len(obj.strokes) < 2:
            raise ValueError('Only multi-contour flattened fills can lose a contour')
        if type(contour_index) is not int or not 0 <= contour_index < len(obj.strokes):
            raise ValueError('Invalid contour index')
        strokes = obj.strokes[:contour_index] + obj.strokes[contour_index + 1:]
        from .tatami import validate_contours
        validate_contours(tuple(s.points for s in strokes))
        self._replace(object_id, replace(obj, strokes=strokes))

    def edit_curve_point(self, object_id: str, path_index: int, segment_index: int,
                         point_index: int, point: Point,
                         *, grid_mm: float | None = None) -> None:
        """Move a retained cubic anchor or handle without flattening the source.

        Shared anchors move together if the old positions match. A gap between
        segments is intentional; joining it behind the user's back would be daft.
        """
        obj = self.object(object_id)
        if obj.kind != 'reference' or not obj.curve_paths:
            raise ValueError('Only reference cubic curves support control-point editing')
        if type(path_index) is not int or not 0 <= path_index < len(obj.curve_paths):
            raise ValueError('Invalid curve path index')
        path = obj.curve_paths[path_index]
        if type(segment_index) is not int or not 0 <= segment_index < len(path.segments):
            raise ValueError('Invalid cubic segment index')
        if type(point_index) is not int or not 0 <= point_index <= 3:
            raise ValueError('Cubic point index must be 0–3')
        if not isinstance(point, Point) or abs(point.x) > 10000 or abs(point.y) > 10000:
            raise ValueError('Cubic control point is outside supported coordinates')
        if grid_mm is not None:
            point = Point(snap_coordinate(point.x, grid_mm),
                          snap_coordinate(point.y, grid_mm))
        old_segments = path.segments
        old_point = getattr(old_segments[segment_index], f'p{point_index}')
        segments = list(old_segments)
        segments[segment_index] = replace(segments[segment_index], **{f'p{point_index}': point})
        # Only synchronise coincident endpoints. Handle directions are independent.
        if point_index in (0, 3):
            neighbour = ((segment_index - 1) % len(segments) if point_index == 0
                         else (segment_index + 1) % len(segments))
            neighbour_attr = 'p3' if point_index == 0 else 'p0'
            wraps = (point_index == 0 and segment_index == 0 or
                     point_index == 3 and segment_index == len(segments) - 1)
            if (not wraps or path.closed) and getattr(old_segments[neighbour], neighbour_attr) == old_point:
                segments[neighbour] = replace(segments[neighbour], **{neighbour_attr: point})
        curves = list(obj.curve_paths)
        curves[path_index] = replace(path, segments=tuple(segments))
        self._replace(object_id, replace(obj, curve_paths=tuple(curves)))

    def set_stitch_kind(self, object_id: str, kind: str) -> None:
        """Only safe conversions: an open line cannot silently become a filled polygon."""
        obj = self.object(object_id)
        if kind not in {'running', 'tatami'} or obj.kind not in {'running', 'tatami'}:
            raise ValueError('Only running and closed tatami objects can be switched here')
        if kind == 'tatami' and (not obj.strokes or any(
                not stroke.closed or len(stroke.points) < 3 for stroke in obj.strokes)):
            raise ValueError('Tatami requires closed paths with at least three vertices')
        if kind == obj.kind:
            return
        self._replace(object_id, replace(obj, kind=kind,
                         settings=replace(obj.settings, style=kind)))

    def reorder(self, object_id: str, destination_index: int) -> None:
        if type(destination_index) is not int or not 0 <= destination_index < len(self.design.objects):
            raise ValueError('Invalid object position')
        objects = list(self.design.objects)
        idx = next((i for i, o in enumerate(objects) if o.object_id == object_id), None)
        if idx is None:
            raise ValueError(f'Unknown object: {object_id}')
        obj = objects.pop(idx)
        objects.insert(destination_index, obj)
        self._apply(replace(self.design, objects=tuple(objects)))

    def _replace(self, object_id: str, updated: EmbroideryObject) -> None:
        self._apply(replace(self.design, objects=tuple(
            updated if obj.object_id == object_id else obj for obj in self.design.objects)))
