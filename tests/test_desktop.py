"""Runs with the optional Qt dependency in the desktop CI job."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication
from tabarc_embroidery.gui import StudioWindow
from tabarc_embroidery.project import load_project

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'multi-object.tbes'


def test_desktop_open_edit_preview_save(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        assert window.editor is not None
        assert window.objects.count() == 3
        window._select('red-line')
        window._change(thread_hex='#456789')
        window._move_object('red-line', 1.0, 2.0)
        assert window.editor.dirty
        window.generate_preview()
        assert window._plan is not None
        assert window.timeline.maximum() > 5
        target = tmp_path / 'saved.tbes'
        window.project_path = target
        assert window.save()
        doc, source = load_project(target.read_bytes())
        assert source == window.editor.source
        assert doc.objects[0].thread_hex == '#456789'
        assert not window.editor.dirty
        window.undo()
        assert window.editor.dirty
    finally:
        # Don't prompt about changes in the offscreen smoke test.
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_desktop_draw_save_and_snap(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        window.draw_action.trigger()
        assert window.view.draw_callback is not None
        window._draw_click(12.3, 14.7)
        window._draw_click(18.8, 21.2)
        assert window.finish_path()
        item = window.editor.object(window.active_id)
        assert item.strokes[0].points[0].x == 12
        assert item.strokes[0].points[1].y == 21
        identifier = window.active_id
        window._move_object(identifier, 0.8, -0.6)
        assert window.editor.object(identifier).strokes[0].points[0].x == 13
        assert window.editor.object(identifier).strokes[0].points[0].y == 14
        window.generate_preview()
        assert window._plan is not None
        window.project_path = tmp_path / 'drawn.tbes'
        assert window.save()
        reloaded, _ = load_project(window.project_path.read_bytes())
        assert reloaded.objects[-1].strokes[0].points[0].x == 13
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_svg_import_separates_paths_and_cancel_drawing():
    app = QApplication.instance() or QApplication([])
    example = Path(__file__).resolve().parent / 'fixtures' / 'multistroke.svg'
    window = StudioWindow(example)
    try:
        from tabarc_embroidery.svg_import import import_svg
        assert window.objects.count() == len(import_svg(example.read_bytes()).strokes)
        window.draw_action.trigger()
        window._draw_click(2, 2)
        window.cancel_path()
        assert not window._draw_points
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()
