"""Actual third-party library conformance check. Skips only when not installed.

CI has a dedicated job that installs [formats], so skipping in that job would
mean a broken CI environment, not a passing independent-validation result.
"""
from pathlib import Path
import pytest

from tabarc_embroidery.dst import export_dst
from tabarc_embroidery.digitise import generate_plan
from tabarc_embroidery.format_bridge import independent_dst_check
from tabarc_embroidery.svg_import import import_svg
from dataclasses import replace
from tabarc_embroidery.model import StitchSettings

lib = pytest.importorskip("pyembroidery", reason="Optional independent decoder is not installed")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("filename,style", [
    ("straight.svg", "running"), ("curve.svg", "running"),
    ("satin.svg", "satin"), ("fill-with-hole.svg", "tatami"),
])
def test_native_dst_independent_reader(filename, style):
    doc = import_svg((FIXTURES / filename).read_bytes())
    doc = replace(doc, settings=StitchSettings(style=style))
    plan = generate_plan(doc)
    report = independent_dst_check(export_dst(plan, filename), plan, library=lib)
    assert report["passed"] is True
    assert report["events_compared"] == len(plan.events)
