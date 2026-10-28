from pathlib import Path
from math import hypot
import hashlib
import json

import pytest

from tabarc_embroidery.cli import main
from tabarc_embroidery.dst import encode_record, export_dst, inspect_dst, read_dst_events
from tabarc_embroidery.model import Document, Point, Stroke, Op
from tabarc_embroidery.preflight import inspect_plan
from tabarc_embroidery.preview import preview_svg
from tabarc_embroidery.project import load_project, save_project
from tabarc_embroidery.running import generate_running
from tabarc_embroidery.svg_import import import_svg, _transform

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return import_svg((FIXTURES / name).read_bytes())


@pytest.mark.parametrize("name", ["straight.svg", "curve.svg", "rectangle.svg", "multistroke.svg"])
def test_vertical_slice(name):
    doc = load(name)
    plan = generate_running(doc)
    encoded = export_dst(plan, name)
    decoded = inspect_dst(encoded)
    assert encoded[:3] == b"LA:"
    assert len(encoded) == 512 + 3 * len(plan.events)
    assert encoded[-3:] == b"\x00\x00\xf3"
    assert decoded.stitch_records == sum(e.opcode == Op.STITCH for e in plan.events)
    assert decoded.jump_records == sum(e.opcode == Op.JUMP for e in plan.events)
    assert decoded.position == (plan.events[-1].x10, plan.events[-1].y10)
    assert encoded == export_dst(generate_running(doc), name)
    assert read_dst_events(encoded) == plan.events
    assert "<svg" in preview_svg(plan)
    assert not [i for i in inspect_plan(plan, 100, 100) if i.severity == "ERROR"]


def test_rect_closed_correctly():
    doc = load("rectangle.svg")
    assert doc.strokes[0].closed
    plan = generate_running(doc)
    last = plan.events[-2]
    assert (last.x10, last.y10) == (100, 80)


def test_jump_splits_without_moving_target():
    doc = Document(250, 250, (Stroke("line", (Point(155, 166), Point(160, 166))),), "dummy")
    plan = generate_running(doc)
    jumps = [e for e in plan.events if e.opcode == Op.JUMP]
    assert len(jumps) > 12
    assert (jumps[-1].x10, jumps[-1].y10) == (1550, 1660)
    prev = (0, 0)
    for e in plan.events[:-1]:
        assert max(abs(e.x10 - prev[0]), abs(e.y10 - prev[1])) <= 121
        prev = (e.x10, e.y10)


@pytest.mark.parametrize("dx", [-121, -120, -81, -40, -13, -5, -3, -1, 0, 1, 3, 5, 13, 40, 81, 120, 121])
def test_dst_signed_axis_encoding_reference_known_cases(dx):
    # Independence caveat: this only checks the record encodings against a
    # separately authored structural decoder in the same application.
    from tabarc_embroidery.model import Event, StitchPlan
    data = export_dst(StitchPlan((Event(Op.STITCH, dx, -dx), Event(Op.END, dx, -dx)), "s"))
    summary = inspect_dst(data)
    assert summary.position == (dx, -dx)


def test_dst_known_single_step_bytes():
    assert encode_record(1, 0, Op.STITCH) == b"\x01\x00\x03"
    assert encode_record(-1, 0, Op.STITCH) == b"\x02\x00\x03"
    assert encode_record(0, 1, Op.STITCH) == b"\x80\x00\x03"
    assert encode_record(0, 0, Op.JUMP) == b"\x00\x00\x83"
    assert encode_record(0, 0, Op.END) == b"\x00\x00\xf3"


def test_project_preserves_geometry_and_svg():
    source = (FIXTURES / "curve.svg").read_bytes()
    doc = import_svg(source)
    restored, original = load_project(save_project(doc, source))
    assert original == source
    assert restored == doc
    assert generate_running(restored) == generate_running(doc)


def test_transformed_curve_within_mm_range():
    doc = load("curve.svg")
    points = doc.strokes[0].points
    assert points[0] == Point(6, 30)
    assert points[-1] == Point(50, 30)
    assert min(p.y for p in points) < 10


def test_viewbox_letterbox_centering():
    doc = import_svg(b'<svg width="100mm" height="50mm" viewBox="0 0 100 100"><path d="M0 0 L100 100"/></svg>')
    assert doc.strokes[0].points == (Point(25, 0), Point(75, 50))


def test_viewbox_none_stretches():
    doc = import_svg(b'<svg width="100mm" height="50mm" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M0 0 L100 100"/></svg>')
    assert doc.strokes[0].points == (Point(0, 0), Point(100, 50))


def test_refuses_partial_import():
    with pytest.raises(ValueError, match="arc"):
        import_svg(b'<svg width="50mm" height="50mm"><path d="M0 0 A10 10 0 0 1 20 20"/></svg>')
    with pytest.raises(ValueError, match="Unsupported SVG element"):
        import_svg(b'<svg width="50mm" height="50mm"><circle cx="20" cy="20" r="10"/></svg>')
    with pytest.raises(ValueError, match="DTD"):
        import_svg(b'<!DOCTYPE svg [<!ENTITY x "bad">]><svg/>')


def test_catches_outside_hoop():
    plan = generate_running(load("straight.svg"))
    assert any(issue.code == "OUTSIDE_HOOP" for issue in inspect_plan(plan, 10, 10))


def test_cli_writes_preview_project_and_roundtrip(tmp_path):
    output = tmp_path / "sample.dst"
    preview = tmp_path / "preview.svg"
    project = tmp_path / "sample.tbes"
    assert main(["convert", str(FIXTURES / "curve.svg"), str(output), "--preview", str(preview), "--project", str(project)]) == 0
    assert output.is_file() and preview.is_file() and project.is_file()
    assert main(["inspect", str(output)]) == 0
    again = tmp_path / "sample-2.dst"
    assert main(["convert", str(project), str(again)]) == 0
    assert inspect_dst(output.read_bytes()).position == inspect_dst(again.read_bytes()).position


def test_cli_blocks_errors(tmp_path):
    output = tmp_path / "fail.dst"
    assert main(["convert", str(FIXTURES / "straight.svg"), str(output), "--hoop", "10x10"]) == 2
    assert not output.exists()


def test_path_shapes_and_nested_transform():
    sample = b'''<svg width="80mm" height="80mm" viewBox="0 0 80 80">
       <g transform="translate(10 3)"><g transform="scale(2)">
       <path d="M0 0 l10 0 h5 v10 q5 5 10 0 t10 0" />
       </g></g></svg>'''
    doc = import_svg(sample)
    p = doc.strokes[0].points
    assert p[0] == Point(10, 3)
    assert p[1] == Point(30, 3)
    assert p[2] == Point(40, 3)
    assert p[3] == Point(40, 23)
    assert p[-1] == Point(80, 23)


def test_cubic_s_reflection_works():
    doc = import_svg(b'<svg width="100mm" height="100mm" viewBox="0 0 100 100"><path d="M0 50 C15 10 25 10 40 50 S65 90 80 50"/></svg>')
    points = doc.strokes[0].points
    assert points[0] == Point(0, 50)
    assert points[-1] == Point(80, 50)
    assert min(p.y for p in points) < 35
    assert max(p.y for p in points) > 65


def test_archive_rejects_unexpected_members():
    from io import BytesIO
    from zipfile import ZipFile
    stream = BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('manifest.json', '{}')
        z.writestr('assets/original.svg', '<svg/>')
        z.writestr('../escape.txt', 'no')
    with pytest.raises(ValueError, match="structure"):
        load_project(stream.getvalue())


def test_many_random_records_roundtrip():
    import random
    from tabarc_embroidery.model import Event, StitchPlan
    random.seed(2041)
    x = y = 0
    events = []
    for _ in range(1500):
        dx, dy = random.randint(-121, 121), random.randint(-121, 121)
        x += dx
        y += dy
        events.append(Event(Op.JUMP if random.randint(0, 3) == 0 else Op.STITCH, x, y))
    events.append(Event(Op.END, x, y))
    plan = StitchPlan(tuple(events), "fixture")
    decoded = inspect_dst(export_dst(plan))
    assert decoded.position == (x, y)
    assert read_dst_events(export_dst(plan)) == plan.events
    assert decoded.jump_records == sum(e.opcode == Op.JUMP for e in plan.events)
    assert decoded.stitch_records == sum(e.opcode == Op.STITCH for e in plan.events)


def test_malformed_svg_units_fail():
    with pytest.raises(ValueError):
        import_svg(b'<svg width="50%" height="50mm"><path d="M0 0 L1 1"/></svg>')
    with pytest.raises(ValueError):
        import_svg(b'<svg width="20mm" height="10mm"><rect width="5mm" height="5"/></svg>')


def test_dst_external_reference_vertical_axis_and_header():
    """Fixed raw-DST byte fixtures for screen-space +Y down versus DST +Y up.

    This prevents the writer and our reader from mutually hiding an axis error.
    Tajima raw record bit positions documented independently by pyembroidery.
    """
    from tabarc_embroidery.model import Event, StitchPlan
    plan = StitchPlan((Event(Op.JUMP, 0, 10), Event(Op.STITCH, 10, 10),
                       Event(Op.END, 10, 10)), "fixture")
    data = export_dst(plan, "axis")
    assert data[512:515] == b"\x50\x00\x83"  # machine -10: negative 1 and negative 9
    assert data[515:518] == b"\x05\x00\x03"  # machine +10: positive 1 and positive 9
    assert data[-3:] == b"\x00\x00\xf3"
    assert read_dst_events(data) == plan.events
    header = data[:512].decode("ascii")
    assert "+Y:    0" in header
    assert "-Y:   10" in header
    assert "AY:   -10" in header
    assert "ST:      2" in header


def test_dst_single_step_absolute_fixed_raw_bytes():
    from tabarc_embroidery.model import Event, StitchPlan
    plan = StitchPlan((Event(Op.STITCH, 0, 1), Event(Op.END, 0, 1)), "fixture")
    assert export_dst(plan)[512:515] == b"\x40\x00\x03"
    assert read_dst_events(export_dst(plan)) == plan.events
