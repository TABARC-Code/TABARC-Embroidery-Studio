"""Generated needle events retain the source object and their original index."""
from hashlib import sha256
import json
import pytest
from tabarc_embroidery.design import (DesignDocument, DesignTrace, EmbroideryObject,
                                     generate_design_plan, generate_design_trace)
from tabarc_embroidery.diagnostics import inspect_needle_trace
from tabarc_embroidery.model import Point, Stroke, StitchSettings, Op, Event, StitchPlan
from tabarc_embroidery.project import load_project, save_project

SHA = sha256(b'synthetic source').hexdigest()


def obj(ident, colour, start, end, *, visible=True):
    return EmbroideryObject(ident, ident, 'running',
        (Stroke(ident, (Point(*start), Point(*end))),), StitchSettings(),
        colour, visible)


def design(*objects):
    return DesignDocument(100, 100, objects, SHA)


def test_trace_agrees_with_original_plan_byte_for_byte():
    d = design(obj('first', '#AA0000', (2, 2), (12, 2)),
               obj('second', '#00AABB', (55, 55), (60, 55)))
    trace = generate_design_trace(d)
    assert trace.plan == generate_design_plan(d)
    assert len(trace.object_ids) == len(trace.plan.events)
    assert trace.object_ids[-1] is None
    assert trace.plan.events[-1].opcode == Op.END
    assert 'first' in trace.object_ids and 'second' in trace.object_ids
    changes = [i for i, event in enumerate(trace.plan.events)
               if event.opcode == Op.COLOUR_CHANGE]
    assert len(changes) == 1
    assert trace.owner_at(changes[0]) == 'second'
    jumps = [i for i, event in enumerate(trace.plan.events)
             if event.opcode == Op.JUMP and trace.object_ids[i] == 'second']
    assert jumps


def test_trace_excludes_hidden_references_and_marks_explicit_controls():
    d = design(obj('sew', '#0A0A0A', (2, 2), (9, 2)),
               obj('hidden', '#0B0B0B', (5, 5), (10, 5), visible=False),
               EmbroideryObject('ref', 'Reference', 'reference'),
               EmbroideryObject('cut', 'Cut', 'trim'))
    trace = generate_design_trace(d)
    assert set(trace.object_ids) == {'sew', 'cut', None}
    assert trace.object_ids[-2] == 'cut'
    assert trace.plan.events[-2].opcode == Op.TRIM


def test_trace_survives_save_reload_without_persisting_indices():
    d = design(obj('a', '#101010', (2, 4), (12, 4)),
               obj('b', '#202020', (30, 4), (32, 4)))
    original = b'synthetic source'
    loaded, source = load_project(save_project(d, original))
    assert source == original
    assert generate_design_trace(loaded) == generate_design_trace(d)


def test_trace_rejects_bad_alignment():
    trace = generate_design_trace(design(obj('a', '#000000', (2, 2), (5, 2))))
    with pytest.raises(ValueError, match='length'):
        DesignTrace(trace.plan, trace.object_ids[:-1])
    with pytest.raises(ValueError, match='END'):
        DesignTrace(trace.plan, trace.object_ids[:-1] + ('a',))


def test_event_diagnostics_report_real_indices_and_positions():
    plan = StitchPlan((Event(Op.JUMP, 20, 20), Event(Op.STITCH, 21, 20),
                       Event(Op.STITCH, 22, 20), Event(Op.STITCH, 23, 20),
                       Event(Op.JUMP, 1500, 20), Event(Op.END, 1500, 20)), SHA)
    trace = DesignTrace(plan, ('a', 'a', 'a', 'a', 'b', None))
    findings = inspect_needle_trace(trace, 100, 100)
    assert [(i.object_id, i.event_index, i.code) for i in findings] == [
        ('a', 2, 'VERY_SHORT_STITCH'), ('b', 4, 'NEEDLE_OUTSIDE_HOOP')]
    assert findings[0].x_mm == 2.2 and findings[0].y_mm == 2
    assert findings[1].severity == 'ERROR'
    assert findings == inspect_needle_trace(trace, 100, 100)
    assert len(inspect_needle_trace(trace, 100, 100, max_findings=1)) == 1


def test_jumps_are_not_measured_as_stitches():
    plan = StitchPlan((Event(Op.JUMP, 100, 50), Event(Op.STITCH, 101, 50),
                       Event(Op.JUMP, 200, 50), Event(Op.STITCH, 201, 50),
                       Event(Op.END, 201, 50)), SHA)
    trace = DesignTrace(plan, ('a', 'a', 'b', 'b', None))
    assert inspect_needle_trace(trace, 100, 100) == []
    with pytest.raises(ValueError):
        inspect_needle_trace(trace, 0, 100)


def test_cli_trace_filter_keeps_global_indices(tmp_path, capsys):
    from tabarc_embroidery.cli import main
    d = design(obj('first', '#AA0000', (2, 2), (12, 2)),
               obj('second', '#00AABB', (55, 55), (60, 55)))
    path = tmp_path / 'sequence.tbes'
    path.write_bytes(save_project(d, b'synthetic source'))
    assert main(['design-trace', str(path), '--object-id', 'second', '--limit', '2']) == 0
    report = json.loads(capsys.readouterr().out)
    trace = generate_design_trace(d)
    expected = [i for i, objid in enumerate(trace.object_ids) if objid == 'second'][:2]
    assert [event['index'] for event in report['events']] == expected
    assert report['total_events'] == len(trace.plan.events)
    assert main(['design-trace', str(path), '--limit', '1001']) == 1
    assert 'limit' in capsys.readouterr().err
    assert main(['design-trace', str(path), '--object-id', 'missing']) == 1
    assert 'Unknown object ID' in capsys.readouterr().err
