"""Static warnings are explanations, not certifications of sewability."""
from dataclasses import replace
from hashlib import sha256

from tabarc_embroidery.design import DesignDocument, EmbroideryObject
from tabarc_embroidery.diagnostics import inspect_design
from tabarc_embroidery.model import Point, Stroke, StitchSettings

SHA = sha256(b'original').hexdigest()


def design(*objects):
    return DesignDocument(100, 100, objects, SHA)


def test_design_diagnostics_are_per_object_and_are_non_mutating():
    source = EmbroideryObject('a', 'A', 'running',
        (Stroke('line', (Point(-1, 10), Point(0, 10), Point(0.1, 10))),),
        StitchSettings(style='running', stitch_length_mm=7))
    original = design(source)
    issues = inspect_design(original)
    assert {(i.object_id, i.code) for i in issues} == {
        ('a', 'GEOMETRY_OUTSIDE_HOOP'), ('a', 'SHORT_SOURCE_EDGES'),
        ('a', 'LONG_RUNNING_SETTING')}
    assert all(i.severity in {'WARNING', 'ERROR', 'INFO'} for i in issues)
    assert original == design(source)
    assert inspect_design(original) == issues


def test_fill_spacing_satins_and_unsupported_controls():
    square = Stroke('shape', (Point(10, 10), Point(10.6, 10),
                              Point(10.6, 30), Point(10, 30)), True)
    fill = EmbroideryObject('fill', 'Fill', 'tatami', (square,),
                            StitchSettings(style='tatami', row_spacing_mm=0.25))
    sat = EmbroideryObject('satin', 'Satin', 'satin', (square, square),
                           StitchSettings(style='satin', max_satin_width_mm=11))
    stop = EmbroideryObject('stop', 'Pause', 'stop')
    ref = EmbroideryObject('ref', 'Reference', 'reference')
    codes = {i.code for i in inspect_design(design(fill, sat, stop, ref))}
    assert {'NARROW_CONTOUR_BOUNDS', 'CLOSE_FILL_ROWS', 'WIDE_SATIN_LIMIT',
            'UNSUPPORTED_DST_CONTROL', 'REFERENCE_NOT_SEWN'} <= codes
    assert not inspect_design(design(replace(fill, visible=False)))


def test_normal_running_path_has_no_spurious_warning():
    obj = EmbroideryObject('good', 'Good', 'running',
                           (Stroke('line', (Point(10, 10), Point(15, 10), Point(20, 10))),),
                           StitchSettings(style='running'))
    assert inspect_design(design(obj)) == []


def test_cli_design_check_returns_json_and_error_exit(tmp_path, capsys):
    import json
    from tabarc_embroidery.cli import main
    from tabarc_embroidery.project import save_project
    from tabarc_embroidery.editor import as_design
    path = tmp_path / 'warning.tbes'
    original = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    from hashlib import sha256
    source = EmbroideryObject('o', 'Outside', 'running',
        (Stroke('line', (Point(-1, 0), Point(5, 5))),), StitchSettings(style='running'))
    doc = DesignDocument(100, 100, (source,), sha256(original).hexdigest())
    path.write_bytes(save_project(doc, original))
    assert main(['design-check', str(path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['errors'] == 1
    assert report['issues'][0]['object_id'] == 'o'
    assert 'not a sew-out' in report['note']
    normal = tmp_path / 'normal.tbes'
    safe = replace(source, strokes=(Stroke('line', (Point(5, 5), Point(10, 10))),))
    normal.write_bytes(save_project(replace(doc, objects=(safe,)), original))
    assert main(['design-check', str(normal)]) == 0
    assert json.loads(capsys.readouterr().out)['errors'] == 0
