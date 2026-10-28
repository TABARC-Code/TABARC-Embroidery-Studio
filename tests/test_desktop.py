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
