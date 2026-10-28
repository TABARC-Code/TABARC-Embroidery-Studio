"""Geometric and DST regression coverage for the second engine milestone."""
from dataclasses import replace
from math import isclose, hypot
from pathlib import Path
import json
import io
import zipfile

import pytest

from tabarc_embroidery.cli import main
from tabarc_embroidery.digitise import generate_plan
from tabarc_embroidery.dst import export_dst, read_dst_events
from tabarc_embroidery.model import Document, Op, Point, StitchSettings, Stroke
from tabarc_embroidery.preflight import inspect_plan
from tabarc_embroidery.project import load_project, save_project
from tabarc_embroidery.satin import generate_satin
from tabarc_embroidery.svg_import import import_svg
from tabarc_embroidery.tatami import generate_tatami, validate_contours

F = Path(__file__).parent / "fixtures"


def rectangle(x1, y1, x2, y2):
    return (Point(x1, y1), Point(x2, y1), Point(x2, y2), Point(x1, y2))


def test_satin_parallel_rails_zigzag_at_correct_width():
    left = (Point(10, 10), Point(40, 10))
    right = (Point(10, 14), Point(40, 14))
    plan = generate_satin(left, right, "s", spacing_mm=.5)
    needle = [e for e in plan.events if e.opcode == Op.STITCH]
    assert len(needle) == 121
    assert needle[0].point_mm == Point(10, 14)
    assert needle[-1].point_mm == Point(40, 14)
    assert all(e.y10 in (100, 140) for e in needle)
    assert not [i for i in inspect_plan(plan, 100, 100) if i.severity == "ERROR"]
    assert read_dst_events(export_dst(plan)) == plan.events


def test_curved_satin_has_bounded_width():
    left = (Point(8, 10), Point(15, 7), Point(25, 10))
    right = (Point(8, 13), Point(15, 11), Point(25, 14))
    plan = generate_satin(left, right, "s", .45)
    assert len(plan.events) > 40
    assert read_dst_events(export_dst(plan)) == plan.events


def test_satin_rejects_crossings_and_too_wide_rails():
    with pytest.raises(ValueError, match="cross"):
        generate_satin((Point(10, 10), Point(30, 30)),
                       (Point(10, 30), Point(30, 10)), "s")
    with pytest.raises(ValueError, match="width"):
        generate_satin((Point(10, 10), Point(30, 10)),
                       (Point(10, 20), Point(30, 20)), "s")
    with pytest.raises(ValueError, match="zero-length"):
        generate_satin((Point(10, 10), Point(10, 10)),
                       (Point(10, 12), Point(30, 12)), "s")
    with pytest.raises(ValueError, match="collapses"):
        generate_satin((Point(10, 10), Point(30, 10)),
                       (Point(10, 10), Point(30, 12)), "s")


@pytest.mark.parametrize("angle", [0, 15, 45, 90, 135, -40])
def test_tatami_rectangle_angles_stay_inside(angle):
    outer = rectangle(10, 10, 50, 40)
    plan = generate_tatami((outer,), "f", row_spacing_mm=.6, angle_deg=angle)
    stitches = [e for e in plan.events if e.opcode == Op.STITCH]
    assert len(stitches) > 100
    for e in stitches:
        p = e.point_mm
        assert 9.94 <= p.x <= 50.06 and 9.94 <= p.y <= 40.06
    assert read_dst_events(export_dst(plan)) == plan.events
    assert not [i for i in inspect_plan(plan, 100, 100) if i.severity == "ERROR"]


def test_tatami_hole_never_stitches_across_hole():
    outer = rectangle(10, 10, 80, 80)
    hole = rectangle(35, 35, 55, 55)
    plan = generate_tatami((outer, hole), "f", .5, 2.5, 0)
    needle = [e for e in plan.events if e.opcode == Op.STITCH]
    assert needle
    previous = Point(0, 0)
    rows_with_hole = 0
    jumps_inside = 0
    for e in plan.events:
        p = e.point_mm
        if e.opcode == Op.STITCH:
            mid = Point((p.x + previous.x)/2, (p.y + previous.y)/2)
            assert not (35.05 < mid.x < 54.95 and 35.05 < mid.y < 54.95), (previous, p)
            if 35 < p.y < 55:
                rows_with_hole += 1
        if e.opcode == Op.JUMP and 35 < p.y < 55:
            jumps_inside += 1
        previous = p
    assert rows_with_hole > 10 and jumps_inside > 10
    assert read_dst_events(export_dst(plan)) == plan.events


def test_disconnected_fill_islands_and_concavity():
    island = rectangle(55, 10, 75, 30)
    concave = (Point(10, 10), Point(40, 10), Point(40, 20),
               Point(20, 20), Point(20, 45), Point(10, 45))
    plan = generate_tatami((concave, island), "f", .7)
    assert any(e.opcode == Op.JUMP for e in plan.events)
    assert len(plan.events) > 100
    # In the notch of the L shape there must be no needle-down stitches.
    assert all(not (22 < e.x10/10 < 38 and 22 < e.y10/10 < 43)
               for e in plan.events if e.opcode == Op.STITCH)


def test_tatami_rejects_crossing_or_self_intersecting_rings():
    bowtie = (Point(5, 5), Point(25, 25), Point(5, 25), Point(25, 5))
    with pytest.raises(ValueError, match="area|intersects"):
        generate_tatami((bowtie,), "f")
    with pytest.raises(ValueError, match="cross or touch"):
        generate_tatami((rectangle(10, 10, 30, 30), rectangle(20, 20, 40, 40)), "f")
    with pytest.raises(ValueError, match="repeated closing"):
        generate_tatami((rectangle(1, 1, 8, 8) + (Point(1, 1),),), "f")


def test_document_settings_are_saved_and_loaded():
    source = (F / "fill-with-hole.svg").read_bytes()
    doc = import_svg(source)
    settings = StitchSettings(style="tatami", row_spacing_mm=.7, angle_deg=30)
    doc = replace(doc, settings=settings)
    blob = save_project(doc, source)
    recovered, original = load_project(blob)
    assert original == source and recovered == doc
    assert generate_plan(recovered) == generate_plan(doc)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["schema_version"] == 2
        assert manifest["stitch_settings"]["style"] == "tatami"


def test_legacy_v1_project_migrates_with_running_default():
    original = (F / "satin.svg").read_bytes()
    doc = import_svg(original)
    data = save_project(doc, original)
    inp = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(inp, "w") as out:
        payload = json.loads(src.read("manifest.json"))
        payload.pop("stitch_settings")
        payload["schema_version"] = 1
        out.writestr("manifest.json", json.dumps(payload))
        out.writestr("assets/original.svg", original)
    recovered, content = load_project(inp.getvalue())
    assert recovered.settings.style == "running" and content == original


def test_cli_satin_and_tatami_and_project_overrides(tmp_path):
    satin = tmp_path / "satin.dst"
    assert main(["convert", str(F / "satin.svg"), str(satin),
                 "--style", "satin", "--satin-spacing-mm", "0.5"]) == 0
    assert satin.exists()
    fill = tmp_path / "fill.dst"
    project = tmp_path / "fill.tbes"
    assert main(["convert", str(F / "fill-with-hole.svg"), str(fill),
                 "--style", "tatami", "--row-mm", "0.65",
                 "--angle-deg", "20", "--project", str(project)]) == 0
    recovered, _ = load_project(project.read_bytes())
    assert recovered.settings.style == "tatami"
    assert isclose(recovered.settings.angle_deg, 20)
    fill2 = tmp_path / "fill-again.dst"
    assert main(["convert", str(project), str(fill2)]) == 0
    assert read_dst_events(fill.read_bytes()) == read_dst_events(fill2.read_bytes())


def test_tatami_continuous_row_turns_do_not_jump_each_row():
    rect = rectangle(10, 10, 50, 45)
    plan = generate_tatami((rect,), "fixture", .5, 2.5)
    jumps = sum(e.opcode == Op.JUMP for e in plan.events)
    # Once inside a rectangle, serpentine turns should be sewn, not jumped.
    assert jumps <= 2, jumps
    prev = Point(0, 0)
    for event in plan.events:
        if event.opcode == Op.STITCH:
            assert hypot(event.point_mm.x - prev.x, event.point_mm.y - prev.y) <= 8.1
        prev = event.point_mm


def test_tatami_avoids_connecting_across_hole_after_quantisation():
    contours = (rectangle(10, 10, 80, 80), rectangle(35, 35, 55, 55))
    plan = generate_tatami(contours, "fixture", row_spacing_mm=.5, stitch_length_mm=2.5)
    assert any(e.opcode == Op.JUMP for e in plan.events)
    previous = Point(0, 0)
    for e in plan.events:
        if e.opcode == Op.STITCH:
            for t in (.25, .5, .75):
                x = previous.x + (e.point_mm.x - previous.x) * t
                y = previous.y + (e.point_mm.y - previous.y) * t
                assert not (35.1 < x < 54.9 and 35.1 < y < 54.9), (previous, e)
        previous = e.point_mm


def test_tatami_obeys_requested_stitch_maximum_with_quantisation_tolerance():
    plan = generate_tatami((rectangle(10, 10, 50, 45),), "fixture", .55, 2.5)
    prev = Point(0, 0)
    for e in plan.events:
        if e.opcode == Op.STITCH:
            assert hypot(e.point_mm.x-prev.x, e.point_mm.y-prev.y) <= 2.6
        prev = e.point_mm


@pytest.mark.parametrize("angle", [0, 17, 45, 90, 127])
def test_rotated_hole_keeps_needle_down_segments_outside(angle):
    contours = (rectangle(10, 10, 65, 65), rectangle(30, 30, 42, 42))
    plan = generate_tatami(contours, "fixture", .8, 2.5, angle)
    previous = Point(0, 0)
    for e in plan.events:
        if e.opcode == Op.STITCH:
            for fraction in (.1, .25, .5, .75, .9):
                x = previous.x + fraction * (e.point_mm.x - previous.x)
                y = previous.y + fraction * (e.point_mm.y - previous.y)
                assert not (30.1 < x < 41.9 and 30.1 < y < 41.9)
        previous = e.point_mm
