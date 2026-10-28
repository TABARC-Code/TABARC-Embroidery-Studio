"""Self-owned synthetic fixtures; publisher artwork is never embedded in tests."""
from __future__ import annotations
import json
import pytest
from tabarc_embroidery.native_project import (load_native_project, inspect_native,
                                               native_geometry_svg, MAX_FILE_BYTES)
from tabarc_embroidery.cli import main


def minimal_object(id=7, style=None, visible=True):
    return {
        'id': id, 'name': 'Needle & <needle>', 'visible': visible,
        'stitch_style': style if style is not None else {'Running': {'spacing_mm': 2.5}},
        'thread_color': [12, 34, 56], 'segments': [
            {'p0': [-2, -1], 'p1': [-1, 0], 'p2': [0, 1], 'p3': [2, 3]}],
        'extra_subpaths': [{'closed': False, 'segments': [
            {'p0': [4, 5], 'p1': [4.2, 6], 'p2': [5, 6], 'p3': [6, 7]}]}],
        'closed': False,
    }


def source(*objects, version=11):
    return json.dumps({'version': version, 'selected_idx': None,
                       'objects': list(objects), 'references': [], 'hoop': None,
                       'branch_groups': [], 'text_boxes': []}).encode('utf8')


def test_native_parsing_and_styles_are_preserved():
    obj = minimal_object()
    p = load_native_project(source(obj, minimal_object(8, 'Guide', visible=False)))
    assert p.schema_version == 11
    assert [o.style for o in p.objects] == ['Running', 'Guide']
    assert p.objects[0].style_parameters['spacing_mm'] == 2.5
    assert len(p.objects[0].paths) == 2
    assert inspect_native(p)['curve_segments'] == 4
    assert inspect_native(p)['style_counts'] == {'Guide': 1, 'Running': 1}
    assert len(p.source_sha256) == 64


def test_native_vector_preview_not_stitches():
    p = load_native_project(source(minimal_object()))
    svg = native_geometry_svg(p)
    assert '<svg ' in svg and '<path ' in svg
    assert 'C -1.000000 0.000000' in svg
    assert 'data-native-name="Needle &amp; &lt;needle&gt;"' in svg
    assert 'stroke="#0c2238"' in svg
    assert 'not native stitch reconstruction' in svg


def test_hidden_and_selected_objects():
    p = load_native_project(source(minimal_object(), minimal_object(9, visible=False)))
    assert 'native-9' not in native_geometry_svg(p)
    assert 'native-9' in native_geometry_svg(p, include_hidden=True)
    assert 'native-7' not in native_geometry_svg(p, include_hidden=True, selected_ids={9})
    with pytest.raises(ValueError, match='Unknown native object IDs'):
        native_geometry_svg(p, selected_ids={55})


@pytest.mark.parametrize('invalid', [
    b'[]', b'not a json', b'{"version":11,"version":11,"objects":[]}',
    b'{"version":11,"objects":[{"id":1,"name":"oops","stitch_style":{"Running":{"spacing_mm":NaN}}}]}',
    b'{"version":11,"objects":[{"id":7,"stitch_style":{"Running":{"spacing_mm":1e9999}}}]}',
    source(minimal_object(), version=999),
    source(minimal_object(), minimal_object()),
])
def test_reject_malformed_projects(invalid):
    with pytest.raises(ValueError):
        load_native_project(invalid)


def test_bad_curve_coordinate_and_rgb():
    a = minimal_object()
    a['segments'][0]['p0'] = [float('inf'), 0]
    with pytest.raises(ValueError):
        load_native_project(source(a))
    a = minimal_object()
    a['thread_color'] = [255, -1, 0]
    with pytest.raises(ValueError):
        load_native_project(source(a))


def test_size_limit_and_empty_svg():
    with pytest.raises(ValueError, match='16 MiB'):
        load_native_project(b' ' * (MAX_FILE_BYTES + 1))
    p = load_native_project(source({'id': 1, 'stitch_style': 'Manual', 'segments': [], 'thread_color': [0, 0, 0]}))
    with pytest.raises(ValueError, match='No visible cubic geometry'):
        native_geometry_svg(p)


def test_native_cli(tmp_path, capsys):
    native = tmp_path / 'example.ostch'
    svg = tmp_path / 'preview.svg'
    native.write_bytes(source(minimal_object()))
    assert main(['native-inspect', str(native)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['objects'] == 1 and report['not_a_stitch_reconstruction']
    assert main(['native-svg', str(native), str(svg)]) == 0
    assert svg.exists() and '<path ' in svg.read_text()
    assert main(['native-svg', str(native), str(tmp_path / 'bad.dst')]) == 1
    assert main(['native-svg', str(native), str(svg), '--object-id', '999']) == 1
