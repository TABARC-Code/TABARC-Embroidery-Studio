"""Contract tests for our adapter. These DO NOT validate real pyembroidery output."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from tabarc_embroidery.cli import main
from tabarc_embroidery.dst import export_dst
from tabarc_embroidery.format_bridge import (
    EXTERNAL_FORMATS, independent_dst_check, pattern_from_plan,
    export_with_pyembroidery, require_pyembroidery,
)
from tabarc_embroidery.model import Event, Op, StitchPlan

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbPattern:
    def __init__(self):
        self.threadlist = []
        self.stitches = []

    def add_thread(self, colour):
        self.threadlist.append(colour)

    def add_stitch_absolute(self, command, x, y):
        self.stitches.append([x, y, command])

    def add_command(self, command):
        x, y = self.stitches[-1][:2] if self.stitches else (0, 0)
        self.stitches.append([x, y, command])


class FakeLibrary:
    EmbPattern = FakeEmbPattern
    STITCH = 0
    JUMP = 1
    COLOR_CHANGE = 5
    END = 4
    COMMAND_MASK = 0xFF
    read_calls = []

    @classmethod
    def write(cls, pattern, filename):
        Path(filename).write_bytes(b"FAKE-DATA")

    @classmethod
    def read_dst(cls, source, settings):
        cls.read_calls.append(settings)
        assert source.read(3) == b"LA:"
        result = FakeEmbPattern()
        result.add_stitch_absolute(cls.JUMP, 0, 10)
        result.add_stitch_absolute(cls.STITCH, 25, 10)
        result.add_command(cls.END)
        return result


def small_plan():
    return StitchPlan((Event(Op.JUMP, 0, 10), Event(Op.STITCH, 25, 10),
                       Event(Op.END, 25, 10)), "sha")


def test_adapter_maps_coordinates_and_commands_without_flipping_y():
    pattern = pattern_from_plan(small_plan(), thread_hex="#1234AB", library=FakeLibrary)
    assert pattern.threadlist == ["#1234AB"]
    assert pattern.stitches == [[0, 10, FakeLibrary.JUMP], [25, 10, FakeLibrary.STITCH],
                                [25, 10, FakeLibrary.END]]


def test_adapter_rejects_invalid_colour_before_calling_writer():
    for value in ["red", "#GGGGGG", "#fff", "000000", "#0000000"]:
        with pytest.raises(ValueError, match="six-digit hex"):
            pattern_from_plan(small_plan(), thread_hex=value, library=FakeLibrary)


def test_external_encoder_routes_by_extension(tmp_path):
    target = tmp_path / "test.pes"
    export_with_pyembroidery(small_plan(), target, library=FakeLibrary)
    assert target.read_bytes() == b"FAKE-DATA"
    assert {"pes", "jef", "vp3", "exp"} <= EXTERNAL_FORMATS


def test_gcode_is_not_an_export_format(tmp_path):
    with pytest.raises(ValueError, match="Unsupported external format"):
        export_with_pyembroidery(small_plan(), tmp_path / "controller.gcode", library=FakeLibrary)


def test_external_reader_contract_checks_coordinates_and_needle_events():
    report = independent_dst_check(export_dst(small_plan()), small_plan(), library=FakeLibrary)
    assert report == {"decoder": "pyembroidery", "passed": True,
                      "events_compared": 3, "stitches_compared": 1, "jumps_compared": 1}
    assert FakeLibrary.read_calls[-1]["clipping"] is False


def test_external_reader_fails_on_wrong_coordinate():
    plan = small_plan()
    wrong = StitchPlan((Event(Op.JUMP, 0, 10), Event(Op.STITCH, 26, 10),
                        Event(Op.END, 26, 10)), "sha")
    with pytest.raises(ValueError, match="Independent DST mismatch"):
        independent_dst_check(export_dst(plan), wrong, library=FakeLibrary)


def test_cli_rejects_controller_and_unverified_formats(tmp_path, capsys):
    result = main(["convert", str(FIXTURES / "straight.svg"),
                   str(tmp_path / "unsafe.gcode")])
    assert result == 1
    assert "Unsupported machine format" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_cli_formats_lists_explicit_backends(capsys):
    assert main(["formats"]) == 0
    output = capsys.readouterr().out
    assert '"native": [\n    "dst"' in output
    assert '"gcode_enabled": false' in output


def test_cli_native_dst_still_works(tmp_path):
    output = tmp_path / "straight.dst"
    assert main(["convert", str(FIXTURES / "straight.svg"), str(output)]) == 0
    assert output.read_bytes().startswith(b"LA:")


def test_cli_external_write_fail_closed_when_dependency_unavailable(tmp_path, monkeypatch, capsys):
    import tabarc_embroidery.format_bridge as bridge

    def missing():
        raise ValueError("No optional dependency in the environment")
    monkeypatch.setattr(bridge, "require_pyembroidery", missing)
    output = tmp_path / "straight.pes"
    assert main(["convert", str(FIXTURES / "straight.svg"), str(output)]) == 1
    assert not output.exists()
    assert not list(tmp_path.glob(".tabarc-export-*"))


def test_cli_independent_check_blocks_export_without_reader(tmp_path, monkeypatch):
    import tabarc_embroidery.format_bridge as bridge
    monkeypatch.setattr(bridge, "require_pyembroidery",
                        lambda: (_ for _ in ()).throw(ValueError("Decoder not installed")))
    target = tmp_path / "straight.dst"
    assert main(["convert", str(FIXTURES / "straight.svg"), str(target),
                 "--independent-check"]) == 1
    assert not target.exists()
