"""No graphical toolkit needed for document edits."""
from dataclasses import replace
from pathlib import Path
import pytest

from tabarc_embroidery.editor import EditorSession, as_design, translate_object
from tabarc_embroidery.model import Document, Point, StitchSettings, Stroke
from tabarc_embroidery.project import load_project, save_project
from tabarc_embroidery.design import generate_design_plan
from tabarc_embroidery.model import Op

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def session(name='multi-object.tbes'):
    document, original = load_project((EXAMPLES / name).read_bytes())
    return EditorSession(as_design(document), original)


def test_edits_persist_and_source_stays_unchanged():
    editor = session()
    old = editor.object('red-line')
    original_source = editor.source
    editor.move('red-line', 2.25, -1.5)
    editor.change('red-line', thread_hex='#aBc123', name='Moved line')
    editor.reorder('red-line', 2)
    editor.change('green-field', visible=False)
    assert editor.dirty
    assert editor.design.objects[-1].object_id == 'red-line'
    restored, asset = load_project(save_project(editor.design, editor.source))
    assert asset == original_source
    moved = restored.objects[-1]
    assert moved.name == 'Moved line' and moved.thread_hex == '#ABC123'
    assert moved.strokes[0].points[0] == Point(old.strokes[0].points[0].x + 2.25,
                                              old.strokes[0].points[0].y - 1.5)
    assert not restored.objects[1].visible
    assert generate_design_plan(restored).thread_palette == ('#0000DD', '#ABC123')


def test_undo_redo_savepoint():
    editor = session()
    editor.change('red-line', thread_hex='#123456')
    assert editor.can_undo and editor.dirty
    editor.undo()
    assert not editor.dirty and editor.can_redo
    editor.redo()
    assert editor.dirty
    editor.mark_saved()
    assert not editor.dirty
    editor.change('red-line', visible=False)
    assert editor.dirty
    editor.undo()
    assert not editor.dirty
    editor.redo()
    editor.change('red-line', name='New idea')
    assert not editor.can_redo


def test_movement_of_cubic_reference_geometry():
    editor = session('synthetic-native-adapted.tbes')
    obj = next(o for o in editor.design.objects if o.curve_paths)
    before = obj.curve_paths[0].segments[0].p1
    editor.move(obj.object_id, 1.5, 2.0)
    after = editor.object(obj.object_id).curve_paths[0].segments[0].p1
    assert after == Point(before.x + 1.5, before.y + 2.0)
    loaded, _ = load_project(save_project(editor.design, editor.source))
    assert next(o for o in loaded.objects if o.object_id == obj.object_id).curve_paths[0].segments[0].p1 == after


def test_legacy_project_upgrades_without_losing_artwork():
    editor = session('curve.tbes')
    assert len(editor.design.objects) == 1
    editor.change('artwork', thread_hex='#345678')
    reloaded, data = load_project(save_project(editor.design, editor.source))
    assert data == editor.source and reloaded.objects[0].thread_hex == '#345678'


def test_invalid_edits_have_no_side_effects():
    editor = session()
    baseline = editor.design
    for edit in (lambda: editor.move('red-line', float('nan'), 0),
                 lambda: editor.change('red-line', thread_hex='red'),
                 lambda: editor.change('red-line', visible=1),
                 lambda: editor.change('red-line', settings=StitchSettings(style='satin')),
                 lambda: editor.reorder('red-line', 999),
                 lambda: editor.move('no-such-id', 1, 0)):
        with pytest.raises(ValueError):
            edit()
        assert editor.design == baseline
    assert not editor.can_undo


def test_reorder_changes_actual_thread_sequence():
    editor = session()
    before = generate_design_plan(editor.design)
    assert before.thread_palette == ('#AA0000', '#0000DD', '#009955')
    editor.reorder('green-field', 0)
    after = generate_design_plan(editor.design)
    assert after.thread_palette == ('#009955', '#AA0000', '#0000DD')
    assert sum(e.opcode == Op.COLOUR_CHANGE for e in after.events) == 2


def test_new_import_is_unsaved_until_written():
    editor = session()
    editor.mark_unsaved()
    assert editor.dirty
    editor.mark_saved()
    assert not editor.dirty


def test_grid_snap_is_absolute_and_has_predictable_midpoints():
    from tabarc_embroidery.editor import snap_coordinate
    assert snap_coordinate(1.25, 0.5) == 1.5
    assert snap_coordinate(-1.25, 0.5) == -1.5
    assert snap_coordinate(1.24, 0.5) == 1.0
    assert snap_coordinate(2.75, 0.5) == 3.0
    for grid in (0, -1, float('nan'), float('inf'), 0.01, 101):
        with pytest.raises(ValueError):
            snap_coordinate(2, grid)
    with pytest.raises(ValueError):
        snap_coordinate(float('nan'), 1.0)


def test_snap_object_anchor_not_relative_delta():
    editor = session()
    obj = editor.object('red-line')
    start = obj.strokes[0].points[0]
    editor.move('red-line', 0.7, 1.3, grid_mm=1)
    moved = editor.object('red-line').strokes[0].points[0]
    from tabarc_embroidery.editor import snap_coordinate
    assert moved == Point(snap_coordinate(start.x + .7, 1),
                          snap_coordinate(start.y + 1.3, 1))
    editor.move('red-line', .12, .12, grid_mm=1)
    assert editor.object('red-line').strokes[0].points[0] == moved
    assert editor.undo()
    assert editor.object('red-line').strokes[0].points[0] == start
    assert not editor.undo()


def test_drawn_path_is_editable_and_saved_without_changing_source():
    editor = session()
    original_source = editor.source
    ident = editor.add_running_path((Point(1, 2), Point(4, 6), Point(7, 9)),
                                    name='Short run', thread_hex='#ab0099')
    assert ident.startswith('drawn-')
    assert editor.object(ident).thread_hex == '#AB0099'
    plan = generate_design_plan(editor.design)
    assert plan.events[-1].opcode == Op.END
    restored, asset = load_project(save_project(editor.design, editor.source))
    assert asset == original_source
    assert restored.objects[-1].strokes[0].points == (Point(1, 2), Point(4, 6), Point(7, 9))
    assert editor.dirty
    editor.undo()
    assert len(editor.design.objects) == len(restored.objects) - 1
    editor.redo()
    assert editor.object(ident).name == 'Short run'


def test_drawing_rejects_bad_geometry_without_mutating_project():
    editor = session()
    before = editor.design
    attempts = (
        ((Point(1, 1),), {}),
        ((Point(1, 1), Point(1, 1)), {}),
        ((Point(1, 1), Point(2, 2)), {'thread_hex': 'red'}),
        ((Point(1, 1), Point(2, 2)), {'name': ''}),
        ((Point(-10001, 1), Point(2, 2)), {}),
    )
    for points, kwargs in attempts:
        with pytest.raises(ValueError):
            editor.add_running_path(points, **kwargs)
        assert editor.design == before
    assert not editor.can_undo


def test_stitch_kind_change_requires_closed_paths():
    from dataclasses import replace
    from tabarc_embroidery.design import EmbroideryObject
    editor = session()
    initial = editor.design
    with pytest.raises(ValueError, match='closed'):
        editor.set_stitch_kind('red-line', 'tatami')
    assert editor.design == initial
    closed = EmbroideryObject('closed', 'Closed square', 'running',
        (Stroke('sq', (Point(20, 20), Point(27, 20), Point(27, 27), Point(20, 27)), True),),
        StitchSettings(style='running'))
    editor._apply(replace(editor.design, objects=editor.design.objects + (closed,)))
    editor.set_stitch_kind('closed', 'tatami')
    assert editor.object('closed').settings.style == 'tatami'
    assert any(e.opcode == Op.STITCH for e in generate_design_plan(editor.design).events)
    editor.set_stitch_kind('closed', 'running')
    assert editor.object('closed').settings.style == 'running'
    with pytest.raises(ValueError):
        editor.set_stitch_kind('closed', 'satin')
