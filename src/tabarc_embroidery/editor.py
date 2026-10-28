"""Headless document editing for the desktop workspace.

The original artwork remains untouched in the project archive. Changing a shape
updates the editable geometry, not the source checksum. Undo is cheap enough for
now; large documents will want a command log rather than whole snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from .design import (CubicSegment, CurvePath, DesignDocument, EmbroideryObject,
                     validate_thread)
from .model import Document, Point, StitchSettings, Stroke

MAX_UNDO = 60


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

    def move(self, object_id: str, dx_mm: float, dy_mm: float) -> None:
        self._replace(object_id, translate_object(self.object(object_id), dx_mm, dy_mm))

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
