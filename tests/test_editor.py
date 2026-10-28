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
