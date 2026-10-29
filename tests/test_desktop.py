"""Runs with the optional Qt dependency in the desktop CI job."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from tabarc_embroidery.model import Point
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


def test_node_mode_moves_real_stitches_and_saves(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        window._select('red-line')
        window.node_action.trigger()
        assert window._node_handles
        obj = window.editor.object('red-line')
        start = obj.strokes[0].points[0]
        window._move_node('red-line', 0, 0, start.x + 1.2, start.y + 2.2)
        assert window.editor.object('red-line').strokes[0].points[0].x == start.x + 1
        window._insert_node('red-line', 0, 0)
        assert len(window._node_handles) == len(obj.strokes[0].points) + 1
        window._delete_node('red-line', 0, 1)
        window.project_path = tmp_path / 'nodes.tbes'
        assert window.save()
        loaded, _ = load_project(window.project_path.read_bytes())
        assert loaded.objects[0].strokes[0].points[0] == window.editor.object('red-line').strokes[0].points[0]
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_desktop_compound_fill_and_undo():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        outer = window.editor.add_running_path((Point(20, 20), Point(70, 20),
                                                 Point(70, 70), Point(20, 70)))
        inner = window.editor.add_running_path((Point(35, 35), Point(55, 35),
                                                 Point(55, 55), Point(35, 55)))
        window.editor.close_contour(outer)
        window.editor.close_contour(inner)
        window._refresh_scene()
        for i in range(window.objects.count()):
            item = window.objects.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in (outer, inner):
                item.setSelected(True)
        window._group_selected()
        assert window.editor.object(window.active_id).kind == 'tatami'
        assert len(window.editor.object(window.active_id).strokes) == 2
        window.undo()
        assert window.active_id is None
        assert window.editor.object(outer) and window.editor.object(inner)
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_desktop_contour_selector_remove_and_diagnostics():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        outer = window.editor.add_running_path((Point(20, 20), Point(70, 20),
                                                 Point(70, 70), Point(20, 70)))
        inner = window.editor.add_running_path((Point(35, 35), Point(55, 35),
                                                 Point(55, 55), Point(35, 55)))
        window.editor.close_contour(outer)
        window.editor.close_contour(inner)
        combined = window.editor.group_fill_contours([outer, inner])
        window.active_id = combined
        window._refresh_scene()
        assert window.contour_combo.count() == 2
        window.node_action.trigger()
        window.contour_combo.setCurrentIndex(1)
        assert len(window._node_handles) == 4
        inner_start = window.editor.object(combined).strokes[1].points[0]
        window._move_node(combined, 1, 0, inner_start.x + 1, inner_start.y + 1)
        assert window.editor.object(combined).strokes[1].points[0] != inner_start
        window._remove_selected_contour()
        assert len(window.editor.object(combined).strokes) == 1
        window.undo()
        assert len(window.editor.object(combined).strokes) == 2
        window.inspect_objects()
        assert window.diagnostics_list.count() >= 0
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_desktop_curve_control_and_warning_selection():
    app = QApplication.instance() or QApplication([])
    reference = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic-native-adapted.tbes'
    window = StudioWindow(reference)
    try:
        oid = next(o.object_id for o in window.editor.design.objects if o.curve_paths)
        window._select(oid)
        window.node_action.trigger()
        assert window._node_handles
        curve = window.editor.object(oid).curve_paths[0].segments[0]
        window._move_curve_point(oid, 0, 0, 1, curve.p1.x + 2, curve.p1.y)
        assert window.editor.object(oid).curve_paths[0].segments[0].p1 != curve.p1
        window.inspect_objects()
        entry = next((window.diagnostics_list.item(i) for i in range(window.diagnostics_list.count())
                      if window.diagnostics_list.item(i).data(Qt.ItemDataRole.UserRole) == oid), None)
        assert entry is not None
        window._select_diagnostic(entry)
        assert window.active_id == oid
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_playback_owners_and_diagnostic_seek():
    from PySide6.QtWidgets import QListWidgetItem
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        window.generate_preview()
        trace = window._trace
        assert trace is not None
        oid = 'red-line'
        index = next(i for i, owner in enumerate(trace.object_ids)
                     if owner == oid and trace.plan.events[i].opcode.value == 'STITCH')
        window.timeline.setValue(index)
        assert window.editor.object(oid).name.lower() in window.position_label.text().lower()
        entry = QListWidgetItem('Needle check')
        entry.setData(Qt.ItemDataRole.UserRole, oid)
        entry.setData(Qt.ItemDataRole.UserRole + 1, index)
        window._select_diagnostic(entry)
        assert window.active_id == oid
        assert window.timeline.value() == index
        window._move_object(oid, 1, 0)
        assert window._trace is None
        assert window._plan is None
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()


def test_inspect_design_populates_trace_without_modifying_geometry():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(EXAMPLE)
    try:
        original = window.editor.design
        window.inspect_objects()
        assert window._trace is not None
        assert window.editor.design == original
        assert window._plan is not None
    finally:
        if window.editor:
            window.editor.mark_saved()
        window.close()
