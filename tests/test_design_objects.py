"""Object-level round trips, fail-closed controls and exact event routing."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from tabarc_embroidery.cli import main
from tabarc_embroidery.design import (DesignDocument, EmbroideryObject, design_from_svg,
                                     design_from_native, generate_design_plan,
                                     promote_reference_running)
from tabarc_embroidery.dst import export_dst, read_dst_events
from tabarc_embroidery.format_bridge import pattern_from_plan
from tabarc_embroidery.model import Event, Op, Point, StitchSettings, Stroke
from tabarc_embroidery.native_project import load_native_project
from tabarc_embroidery.preview import preview_svg
from tabarc_embroidery.project import load_project, save_project

SIMPLE = b'''<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm"
    viewBox="0 0 80 80">
    <path d="M10 10 L30 10"/>
    <path d="M10 20 L30 20"/>
    <path d="M10 35 L30 35 L30 55 L10 55 Z"/>
</svg>'''

ASSIGN = {'objects': [
    {'id': 'top', 'kind': 'running', 'stroke_indices': [0], 'thread_hex': '#AA0000',
     'settings': {'stitch_length_mm': 2.0}},
    {'id': 'bottom', 'kind': 'running', 'stroke_indices': [1], 'thread_hex': '#0000DD'},
    {'id': 'fill', 'kind': 'tatami', 'stroke_indices': [2], 'thread_hex': '#009955',
     'settings': {'row_spacing_mm': 1.0, 'stitch_length_mm': 3.0}},
]}


def two_colour():
    return design_from_svg(SIMPLE, {'objects': ASSIGN['objects'][:2] + [
        {'id': 'reference', 'kind': 'reference', 'stroke_indices': [2]}]})


def test_multi_object_sewing_order_and_colour_transitions():
    design = two_colour()
    plan = generate_design_plan(design)
    assert plan.thread_palette == ('#AA0000', '#0000DD')
    changes = [i for i, event in enumerate(plan.events) if event.opcode == Op.COLOUR_CHANGE]
    assert len(changes) == 1
    change = changes[0]
    assert plan.events[change].point_mm == plan.events[change - 1].point_mm
    # First next event travels with needle raised; never sew between objects.
    assert plan.events[change + 1].opcode == Op.JUMP
    assert plan.events[change + 1].y10 > plan.events[change].y10
    assert read_dst_events(export_dst(plan)) == plan.events
    preview = preview_svg(plan)
    assert 'stroke="#AA0000"' in preview and 'stroke="#0000DD"' in preview
    assert 'colour-change' in preview


def test_three_objects_with_tatami_and_project_schema3_round_trip():
    design = design_from_svg(SIMPLE, ASSIGN)
    blob = save_project(design, SIMPLE)
    restored, source = load_project(blob)
    assert source == SIMPLE
    assert restored == design
    assert 'assets/source.svg' in ZipFile(io.BytesIO(blob)).namelist()
    plan = generate_design_plan(restored)
    assert plan.thread_palette == ('#AA0000', '#0000DD', '#009955')
    assert sum(e.opcode == Op.COLOUR_CHANGE for e in plan.events) == 2
    assert read_dst_events(export_dst(plan)) == plan.events
    assert sum(e.opcode == Op.STITCH for e in plan.events) > 50


def test_controls_are_distinct_and_not_silently_exported():
    design = two_colour()
    controls = (
        EmbroideryObject('trim1', 'Trim thread', 'trim'),
        EmbroideryObject('stop1', 'Operator pause', 'stop'),
    )
    amended = replace(design, objects=design.objects[:1] + controls + design.objects[1:])
    plan = generate_design_plan(amended)
    assert [e.opcode for e in plan.events if e.opcode in {Op.TRIM, Op.STOP}] == [Op.TRIM, Op.STOP]
    with pytest.raises(ValueError, match='TRIM or STOP'):
        export_dst(plan)
    with pytest.raises(ValueError, match='STOP'):
        pattern_from_plan(plan, library=object())


def test_explicit_colour_change_and_same_colour_segment():
    design = two_colour()
    objects = design.objects
    colour = EmbroideryObject('thread', 'Swap spool', 'colour_change', thread_hex='#AA0000')
    new = replace(design, objects=(objects[0], colour, objects[1], objects[2]))
    plan = generate_design_plan(new)
    assert plan.thread_palette == ('#AA0000', '#AA0000', '#0000DD')
    assert sum(e.opcode == Op.COLOUR_CHANGE for e in plan.events) == 2
    assert read_dst_events(export_dst(plan)) == plan.events


def test_same_colour_across_objects_avoids_unneeded_stop():
    design = two_colour()
    matched = replace(design.objects[1], thread_hex='#AA0000')
    plan = generate_design_plan(replace(design, objects=(design.objects[0], matched, design.objects[2])))
    assert plan.thread_palette == ('#AA0000',)
    assert not any(e.opcode == Op.COLOUR_CHANGE for e in plan.events)
    assert plan.events[-1].opcode == Op.END


def test_invisible_stitch_objects_do_not_export_or_change_palette():
    design = two_colour()
    hidden = replace(design.objects[1], visible=False)
    plan = generate_design_plan(replace(design, objects=(design.objects[0], hidden, design.objects[2])))
    assert plan.thread_palette == ('#AA0000',)
    assert all(e.y10 <= 100 for e in plan.events)


def test_rejects_silent_dropped_svg_paths():
    with pytest.raises(ValueError, match='Unassigned SVG paths'):
        design_from_svg(SIMPLE, {'objects': ASSIGN['objects'][:2]})


def test_prevent_satin_underdefined_and_reference_only_sewing():
    from tabarc_embroidery.design import EmbroideryObject
    design = two_colour()
    with pytest.raises(ValueError, match='Satin needs exactly two'):
        generate_design_plan(replace(design, objects=(
            replace(design.objects[0], kind='satin', settings=StitchSettings(style='satin')),)))
    with pytest.raises(ValueError, match='no stitchable'):
        generate_design_plan(replace(design, objects=(design.objects[-1],)))


def test_rejects_same_object_ids_and_mismatch_styles():
    design = two_colour()
    with pytest.raises(ValueError, match='Duplicate'):
        replace(design, objects=(design.objects[0], design.objects[0]))
    with pytest.raises(ValueError, match='settings must match'):
        replace(design.objects[0], kind='satin')


def test_control_cannot_reposition_needle_in_machine_plan():
    design = two_colour()
    plan = generate_design_plan(design)
    for i, event in enumerate(plan.events[1:]):
        if event.opcode == Op.COLOUR_CHANGE:
            assert (event.x10, event.y10) == (plan.events[i].x10, plan.events[i].y10)


def test_cli_compose_convert_inspect_roundtrip(tmp_path, capsys):
    source = tmp_path / 'art.svg'
    config = tmp_path / 'style.json'
    project = tmp_path / 'art.tbes'
    output = tmp_path / 'art.dst'
    preview = tmp_path / 'view.svg'
    source.write_bytes(SIMPLE)
    config.write_text(json.dumps(ASSIGN))
    assert main(['compose', str(source), str(config), str(project)]) == 0
    assert main(['design-inspect', str(project)]) == 0
    assert 'tatami' in capsys.readouterr().out
    assert main(['convert', str(project), str(output), '--preview', str(preview)]) == 0
    assert output.read_bytes().startswith(b'LA:')
    assert 'stroke="#009955"' in preview.read_text()
    second = tmp_path / 'second.dst'
    assert main(['convert', str(project), str(second), '--style', 'running']) == 1
    assert not second.exists()


def test_cli_rejects_trim_output_with_no_partial_write(tmp_path):
    source = tmp_path / 'art.svg'; source.write_bytes(SIMPLE)
    config = tmp_path / 'assignment.json'; project = tmp_path / 'art.tbes'
    config.write_text(json.dumps({'objects': ASSIGN['objects'][:1] + [
        {'id': 'trim', 'kind': 'trim'}, *ASSIGN['objects'][1:]]}))
    assert main(['compose', str(source), str(config), str(project)]) == 0
    target = tmp_path / 'out.dst'
    assert main(['convert', str(project), str(target)]) == 1
    assert not target.exists()


def test_native_reference_roundtrip_preserves_original_control_points(tmp_path):
    source = (Path(__file__).parent.parent / 'examples' / 'synthetic-native.ostch').read_bytes()
    native = load_native_project(source)
    doc = design_from_native(native)
    assert doc.source_format == 'ostch'
    assert doc.objects[0].original_style == 'Running'
    assert doc.objects[0].curve_paths[0].segments[0].p1 == Point(8, -4)
    restored, original = load_project(save_project(doc, source))
    assert restored == doc and original == source
    with pytest.raises(ValueError, match='no stitchable'):
        generate_design_plan(restored)
    adapted = tmp_path / 'adapted.tbes'
    path = tmp_path / 'input.ostch'; path.write_bytes(source)
    assert main(['native-adapt', str(path), str(adapted)]) == 0
    assert main(['design-inspect', str(adapted)]) == 0
    promoted = tmp_path / 'promoted.tbes'
    assert main(['design-promote-running', str(adapted), '1001', str(promoted)]) == 0
    prom, orig = load_project(promoted.read_bytes())
    assert prom.objects[0].kind == 'running'
    assert prom.objects[0].curve_paths == doc.objects[0].curve_paths
    assert len(prom.objects[0].strokes[0].points) > 3
    assert orig == source


def test_native_cubic_malformed_length_is_rejected_not_silently_dropped():
    source = (Path(__file__).parent.parent / 'examples' / 'synthetic-native.ostch').read_bytes()
    blob = save_project(design_from_native(load_native_project(source)), source)
    with ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    manifest['objects'][0]['curve_paths'][0]['segments'][0].pop()
    out = io.BytesIO()
    with ZipFile(out, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('assets/source.ostch', source)
    with pytest.raises(ValueError, match='four control'):
        load_project(out.getvalue())


def test_colour_sequence_pattern_adapter_handles_palette():
    class Pattern:
        def __init__(self):
            self.threadlist = []
            self.stitches = []
        def add_thread(self, v): self.threadlist.append(v)
        def add_stitch_absolute(self, op, x, y): self.stitches.append((op, x, y))
        def add_command(self, op): self.stitches.append((op,))
    class Lib:
        EmbPattern = Pattern
        STITCH = 0; JUMP = 1; COLOR_CHANGE = 5; TRIM = 2; END = 4
    plan = generate_design_plan(two_colour())
    p = pattern_from_plan(plan, library=Lib)
    assert p.threadlist == ['#AA0000', '#0000DD']
    assert any(s[0] == Lib.COLOR_CHANGE for s in p.stitches)
    bad = replace(plan, thread_palette=('#AABBCC',))
    with pytest.raises(ValueError, match='palette'):
        pattern_from_plan(bad, library=Lib)


def test_explicit_trim_uses_pyembroidery_command_when_supported():
    from test_format_bridge import FakeLibrary
    class TrimmingFake(FakeLibrary):
        TRIM = 2
    design = two_colour()
    with_trim = replace(design, objects=(design.objects[0], EmbroideryObject('tr', 'trim', 'trim'),
                                        design.objects[1], design.objects[2]))
    pat = pattern_from_plan(generate_design_plan(with_trim), library=TrimmingFake)
    assert any(stitch[2] == 2 for stitch in pat.stitches)


def test_satin_and_tatami_objects_share_one_machine_plan():
    svg = b'''<svg width="70mm" height="70mm" viewBox="0 0 70 70">
    <path d="M5 5 L5 28"/><path d="M9 5 L9 28"/>
    <path d="M30 10 L50 10 L50 30 L30 30 Z"/>
    </svg>'''
    doc = design_from_svg(svg, {'objects': [
        {'id': 'column', 'kind': 'satin', 'stroke_indices': [0, 1],
         'thread_hex': '#BB2200', 'settings': {'satin_spacing_mm': 0.6}},
        {'id': 'body', 'kind': 'tatami', 'stroke_indices': [2],
         'thread_hex': '#0044CC', 'settings': {'row_spacing_mm': 0.8}},
    ]})
    plan = generate_design_plan(doc)
    assert plan.thread_palette == ('#BB2200', '#0044CC')
    assert [ev.opcode for ev in plan.events].count(Op.COLOUR_CHANGE) == 1
    assert read_dst_events(export_dst(plan)) == plan.events
    assert len(plan.events) > 100


def test_rapid_colour_changes_at_same_position_are_preserved():
    original = two_colour()
    control = EmbroideryObject('swap1', 'Replace spool', 'colour_change', thread_hex='#00FF00')
    control2 = EmbroideryObject('swap2', 'Replace again', 'colour_change', thread_hex='#778899')
    amended = replace(original, objects=(original.objects[0], control, control2,
                                         original.objects[1], original.objects[2]))
    plan = generate_design_plan(amended)
    assert plan.thread_palette == ('#AA0000', '#00FF00', '#778899', '#0000DD')
    assert read_dst_events(export_dst(plan)) == plan.events


def test_preview_marks_trim_and_stop_without_mislabel_as_stitches():
    original = two_colour()
    trim = EmbroideryObject('tr', 'trim', 'trim')
    stop = EmbroideryObject('st', 'stop', 'stop')
    amended = replace(original, objects=(original.objects[0], trim, stop,
                                         original.objects[1], original.objects[2]))
    svg = preview_svg(generate_design_plan(amended))
    assert svg.count('class="control"') == 2
    assert svg.count('class="colour-change"') == 1


def test_reference_promotion_rejects_unknown_source_style_and_routing_metadata():
    original = (Path(__file__).parent.parent / 'examples' / 'synthetic-native.ostch').read_bytes()
    document = design_from_native(load_native_project(original))
    with pytest.raises(ValueError, match='Unknown object'):
        promote_reference_running(document, 'other-id')
    unrecognised = replace(document.objects[0], original_style='SatinColumn')
    with pytest.raises(ValueError, match='Only native Running'):
        promote_reference_running(replace(document, objects=(unrecognised,)), '1001')
    unrendered = replace(document.objects[0], unrendered_features=('manual_points',))
    with pytest.raises(ValueError, match='unrendered features'):
        promote_reference_running(replace(document, objects=(unrendered,)), '1001')
