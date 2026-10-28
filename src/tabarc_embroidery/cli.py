"""Headless phase-one conversion tool; Qt editor arrives in a later phase."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import importlib.util
import os
import tempfile

from . import __version__
from .dst import export_dst, inspect_dst, read_dst_events
from .preflight import inspect_plan
from .preview import preview_svg
from .project import load_project, save_project
from .digitise import generate_plan
from .design import (DesignDocument, design_from_svg, design_from_native,
                     generate_design_plan, promote_reference_running)
from .svg_import import import_svg
from .native_project import load_native_project, inspect_native, native_geometry_svg
from .format_bridge import (EXTERNAL_FORMATS, SUPPORTED_FORMATS, export_with_pyembroidery,
                            independent_dst_check)


def _hoop(value: str) -> tuple[float, float]:
    try:
        w, h = value.lower().split("x")
        width, height = float(w), float(h)
        if not (1 <= width <= 2000 and 1 <= height <= 2000):
            raise ValueError
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use hoop dimensions in mm, e.g. 100x100") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tabarc-embroidery",
                                     description="Experimental SVG embroidery digitiser and machine-format exporter")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert", help="Digitise SVG or .tbes project into a supported embroidery format")
    convert.add_argument("source", type=Path)
    convert.add_argument("output", type=Path)
    convert.add_argument("--style", choices=("running", "satin", "tatami"),
                         help="Explicit digitising style (default: saved project or running)")
    convert.add_argument("--stitch-mm", type=float, help="Running or tatami maximum length")
    convert.add_argument("--row-mm", type=float, help="Tatami row spacing")
    convert.add_argument("--angle-deg", type=float, help="Tatami fill angle")
    convert.add_argument("--satin-spacing-mm", type=float, help="Satin zigzag row spacing")
    convert.add_argument("--max-satin-width-mm", type=float, help="Satin width limit")
    convert.add_argument("--tolerance-mm", type=float, default=0.06)
    convert.add_argument("--hoop", type=_hoop, default=(100.0, 100.0))
    convert.add_argument("--preview", type=Path, help="Optional needle-order .svg preview")
    convert.add_argument("--project", type=Path, help="Optional editable .tbes project")
    convert.add_argument("--thread-hex", default="#000000",
                         help="Placeholder thread colour for external formats, e.g. #206040")
    convert.add_argument("--independent-check", action="store_true",
                         help="Verify generated DST using installed pyembroidery; fail closed")
    convert.add_argument("--allow-errors", action="store_true",
                         help="Write despite preflight errors (NOT recommended)")
    native_inspect = commands.add_parser("native-inspect", help="Inspect a native .ostch JSON project (read-only)")
    native_inspect.add_argument("source", type=Path)
    native_svg = commands.add_parser("native-svg", help="Export native cubic geometry to SVG (NOT embroidery stitches)")
    native_svg.add_argument("source", type=Path)
    native_svg.add_argument("output", type=Path)
    native_svg.add_argument("--include-hidden", action="store_true")
    native_svg.add_argument("--object-id", type=int, action="append", default=None,
                            help="Include only specific native object IDs; may be repeated")
    compose = commands.add_parser("compose", help="Assign per-object stitch settings from SVG and JSON; save schema-3 .tbes")
    compose.add_argument("source", type=Path)
    compose.add_argument("assignments", type=Path)
    compose.add_argument("output", type=Path)
    native_adapt = commands.add_parser("native-adapt", help="Preserve observed .ostch objects as NON-SEWING reference geometry")
    native_adapt.add_argument("source", type=Path)
    native_adapt.add_argument("output", type=Path)
    promote = commands.add_parser("design-promote-running", help="Explicitly approximate one native Running reference as stitches")
    promote.add_argument("source", type=Path)
    promote.add_argument("object_id")
    promote.add_argument("output", type=Path)
    design_inspect = commands.add_parser("design-inspect", help="List objects, settings and source metadata in .tbes")
    design_inspect.add_argument("source", type=Path)
    commands.add_parser("formats", help="List output formats and optional dependency status")
    inspect = commands.add_parser("inspect", help="Inspect basic DST structure and bounds")
    inspect.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compose":
            if args.source.suffix.lower() != '.svg' or args.output.suffix.lower() != '.tbes':
                raise ValueError('compose requires .svg input and .tbes output')
            if args.assignments.stat().st_size > 1_000_000:
                raise ValueError('Assignment specification exceeds 1 MiB')
            spec = json.loads(args.assignments.read_text(encoding='utf-8'),
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
            original = args.source.read_bytes()
            doc = design_from_svg(original, spec)
            result = save_project(doc, original)
            args.output.write_bytes(result)
            print(json.dumps({'output': str(args.output), 'schema': 3,
                              'objects': len(doc.objects), 'source_sha256': doc.source_sha256}))
            return 0
        if args.command == 'native-adapt':
            if args.source.suffix.lower() != '.ostch' or args.output.suffix.lower() != '.tbes':
                raise ValueError('native-adapt requires .ostch input and .tbes output')
            source = args.source.read_bytes()
            native = load_native_project(source)
            doc = design_from_native(native)
            args.output.write_bytes(save_project(doc, source))
            print(json.dumps({'objects_preserved_as_reference': len(doc.objects),
                              'output': str(args.output), 'sewable_objects': 0,
                              'warning': 'No source stitch style has been interpreted or converted'}))
            return 0
        if args.command == 'design-promote-running':
            if args.source.suffix.lower() != '.tbes' or args.output.suffix.lower() != '.tbes':
                raise ValueError('design-promote-running requires .tbes input/output')
            doc, original = load_project(args.source.read_bytes())
            if not isinstance(doc, DesignDocument) or doc.source_format != 'ostch':
                raise ValueError('Expected an adapted native reference project')
            promoted = promote_reference_running(doc, args.object_id)
            args.output.write_bytes(save_project(promoted, original))
            print(json.dumps({'output': str(args.output), 'promoted': args.object_id,
                              'warning': 'Experimental Running approximation; not exact native stitches'}))
            return 0
        if args.command == 'design-inspect':
            if args.source.suffix.lower() != '.tbes':
                raise ValueError('design-inspect expects a .tbes project')
            document, _ = load_project(args.source.read_bytes())
            if not isinstance(document, DesignDocument):
                print(json.dumps({'schema': 'legacy', 'strokes': len(document.strokes),
                                  'style': document.settings.style}))
                return 0
            print(json.dumps({'schema': 3, 'source_format': document.source_format,
                              'source_sha256': document.source_sha256,
                              'objects': [{'id': o.object_id, 'name': o.name,
                                           'kind': o.kind, 'thread_hex': o.thread_hex,
                                           'visible': o.visible, 'source_style': o.original_style,
                                           'stroke_count': len(o.strokes),
                                           'curve_segments': sum(len(p.segments) for p in o.curve_paths),
                                           'unrendered_features': list(o.unrendered_features)}
                                          for o in document.objects]}, indent=2))
            return 0
        if args.command in {"native-inspect", "native-svg"}:
            if args.source.suffix.lower() != ".ostch":
                raise ValueError("Expected a .ostch project")
            if args.source.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Native project exceeds 16 MiB limit")
            native = load_native_project(args.source.read_bytes())
            if args.command == "native-inspect":
                print(json.dumps(inspect_native(native), indent=2))
            else:
                if args.output.suffix.lower() != ".svg":
                    raise ValueError("Native geometry output must be .svg")
                svg = native_geometry_svg(native, include_hidden=args.include_hidden,
                                          selected_ids=set(args.object_id) if args.object_id else None)
                args.output.write_text(svg, encoding="utf-8")
                print(json.dumps({"output": str(args.output),
                                  "warning": "Geometry only: native stitch settings, underlay, travel and stops are NOT regenerated"}))
            return 0
        if args.command == "formats":
            print(json.dumps({"native": ["dst"], "optional": sorted(EXTERNAL_FORMATS),
                              "pyembroidery_installed": importlib.util.find_spec("pyembroidery") is not None,
                              "gcode_enabled": False}, indent=2))
            return 0
        if args.command == "inspect":
            summary = inspect_dst(args.source.read_bytes())
            print(json.dumps(summary.__dict__, indent=2))
            return 0
        format_name = args.output.suffix.lower().lstrip(".")
        if format_name not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported machine format .{format_name}; run formats to list options")
        if args.independent_check and format_name != "dst":
            raise ValueError("--independent-check currently requires DST export")
        data = args.source.read_bytes()
        if args.source.suffix.lower() == ".tbes":
            doc, original = load_project(data)
        elif args.source.suffix.lower() == ".svg":
            original = data
            doc = import_svg(data, tolerance_mm=args.tolerance_mm)
        else:
            raise ValueError("Input must be .svg or .tbes")
        overrides = {key: value for key, value in {
            "style": args.style, "stitch_length_mm": args.stitch_mm,
            "row_spacing_mm": args.row_mm, "angle_deg": args.angle_deg,
            "satin_spacing_mm": args.satin_spacing_mm,
            "max_satin_width_mm": args.max_satin_width_mm,
        }.items() if value is not None}
        if isinstance(doc, DesignDocument):
            if overrides:
                raise ValueError('Global stitch overrides are unavailable for per-object projects')
            if args.thread_hex != '#000000':
                raise ValueError('--thread-hex cannot override a per-object thread palette')
            plan = generate_design_plan(doc)
            style = 'multi-object'
            stroke_count = sum(len(o.strokes) for o in doc.objects)
        else:
            if overrides:
                doc = replace(doc, settings=replace(doc.settings, **overrides))
            plan = generate_plan(doc)
            style = doc.settings.style
            stroke_count = len(doc.strokes)
        errors = inspect_plan(plan, *args.hoop)
        report = {"style": style, "strokes": stroke_count,
                  "colour_segments": len(plan.thread_palette) or 1,
                  "controls": {kind: sum(e.opcode.value == kind for e in plan.events)
                               for kind in ('TRIM', 'STOP', 'COLOUR_CHANGE')},
                  "stitches": sum(e.opcode.value == "STITCH" for e in plan.events),
                  "needle_events": len(plan.events), "document_mm": [doc.width_mm, doc.height_mm],
                  "hoop_mm": list(args.hoop), "issues": [i.__dict__ for i in errors]}
        if any(e.severity == "ERROR" for e in errors) and not args.allow_errors:
            print(json.dumps(report, indent=2))
            print("Export blocked by preflight errors. See report above.", file=sys.stderr)
            return 2
        if format_name == "dst":
            result = export_dst(plan, label=args.source.stem)
            # Check our local reader first; optional independent decoder next.
            decoded = inspect_dst(result)
            if decoded.position != (plan.events[-1].x10, plan.events[-1].y10):
                raise ValueError("DST read-back needle position differs from planned output")
            if decoded.stitch_records != report["stitches"]:
                raise ValueError("DST read-back stitch count differs from planned output")
            if read_dst_events(result) != plan.events:
                raise ValueError("DST read-back event stream differs from the needle-order preview")
            if args.independent_check:
                report["independent_dst_check"] = independent_dst_check(result, plan)
            # No file is created if the cross-check fails.
            args.output.write_bytes(result)
            report["export_backend"] = "native"
        else:
            # External writers select encoder by extension; leave the suffix
            # intact on the temporary file and don't replace a good file if
            # the optional dependency fails.
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=".tabarc-export-", suffix=args.output.suffix,
                    dir=args.output.parent, delete=False
                ) as handle:
                    temporary_path = Path(handle.name)
                export_with_pyembroidery(plan, temporary_path,
                                         thread_hex=args.thread_hex)
                os.replace(temporary_path, args.output)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            report["export_backend"] = "pyembroidery"
            report["thread_note"] = "Thread colour is a placeholder, not a brand/thread-chart match"
        print(json.dumps(report, indent=2))
        if args.preview:
            args.preview.write_text(preview_svg(plan), encoding="utf-8")
        if args.project:
            args.project.write_bytes(save_project(doc, original))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
