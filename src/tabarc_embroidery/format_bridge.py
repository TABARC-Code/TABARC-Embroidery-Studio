"""Optional pyembroidery bridge. No third-party code is vendored into this package.

All stitch coordinates use the same +Y-down, 0.1 mm grid as pyembroidery.
The external writer may normalise events or insert extra commands; this is
therefore a *format export*, not proof of machine compatibility.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from .model import Op, StitchPlan

# Deliberately exclude G-code: it can command physical machine hardware and
# needs a machine-specific, separately reviewed implementation.
EXTERNAL_FORMATS = frozenset({"pes", "pec", "exp", "jef", "vp3", "xxx", "u01", "tbf"})
NATIVE_FORMATS = frozenset({"dst"})
SUPPORTED_FORMATS = NATIVE_FORMATS | EXTERNAL_FORMATS


def require_pyembroidery() -> Any:
    try:
        return importlib.import_module("pyembroidery")
    except ImportError as exc:
        raise ValueError(
            "This output needs the optional pyembroidery dependency. "
            "Install with: python -m pip install -e '.[formats]'"
        ) from exc


def pattern_from_plan(plan: StitchPlan, *, thread_hex: str = "#000000", library: Any = None) -> Any:
    """Convert a plan into a pyembroidery EmbPattern without losing colour order.

    TRIM uses pyembroidery's explicit command only when the installed version
    exposes it. STOP is deliberately rejected: never relabel it as a colour
    change without a confirmed machine-specific export policy.
    """
    from .design import validate_thread
    fallback = validate_thread(thread_hex)
    lib = library if library is not None else require_pyembroidery()
    if any(e.opcode == Op.STOP for e in plan.events):
        raise ValueError("Operator STOP cannot yet be exported faithfully; export blocked")
    if any(e.opcode == Op.TRIM for e in plan.events) and not hasattr(lib, 'TRIM'):
        raise ValueError("pyembroidery backend cannot represent explicit TRIM")
    expected_colours = 1 + sum(e.opcode == Op.COLOUR_CHANGE for e in plan.events)
    palette = plan.thread_palette or (fallback,) * expected_colours
    if len(palette) != expected_colours:
        raise ValueError("Thread palette must have one entry per colour segment")
    pattern = lib.EmbPattern()
    for colour in palette:
        pattern.add_thread(validate_thread(colour))
    last = (0, 0)
    commands = {Op.STITCH: lib.STITCH, Op.JUMP: lib.JUMP,
                Op.COLOUR_CHANGE: lib.COLOR_CHANGE}
    if hasattr(lib, 'TRIM'):
        commands[Op.TRIM] = lib.TRIM
    for event in plan.events:
        if event.opcode == Op.END:
            if (event.x10, event.y10) != last:
                raise ValueError("END does not match the last needle position")
            pattern.add_command(lib.END)
        elif event.opcode == Op.TRIM:
            if (event.x10, event.y10) != last:
                raise ValueError("TRIM must not move the needle")
            pattern.add_command(lib.TRIM)
        else:
            if event.opcode == Op.COLOUR_CHANGE and (event.x10, event.y10) != last:
                raise ValueError("COLOUR_CHANGE must not move the needle")
            pattern.add_stitch_absolute(commands[event.opcode], event.x10, event.y10)
            last = (event.x10, event.y10)
    return pattern


def export_with_pyembroidery(
    plan: StitchPlan, target: Path, *, thread_hex: str = "#000000", library: Any = None
) -> None:
    """Write only explicitly supported machine formats, never controller G-code."""
    suffix = target.suffix.lower().lstrip(".")
    if suffix not in EXTERNAL_FORMATS:
        raise ValueError(f"Unsupported external format: .{suffix}")
    lib = library if library is not None else require_pyembroidery()
    pattern = pattern_from_plan(plan, thread_hex=thread_hex, library=lib)
    # pyembroidery chooses a writer from the target extension; no conversion
    # settings have been applied without a machine profile / machine test.
    lib.write(pattern, str(target))
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError("External writer did not produce a file")


def independent_dst_check(
    data: bytes, plan: StitchPlan, *, library: Any = None
) -> dict[str, int | str | bool]:
    """Decode native DST with an independent library and compare needle events.

    The reader's automatic inferred trims are disabled. This is still only a
    decoder check, and does not replace viewer inspection or a physical sew-out.
    """
    from io import BytesIO

    lib = library if library is not None else require_pyembroidery()
    decoded = lib.read_dst(BytesIO(data), {"trim_at": 1000000, "clipping": False})
    commands = {lib.STITCH: Op.STITCH, lib.JUMP: Op.JUMP,
                lib.COLOR_CHANGE: Op.COLOUR_CHANGE, lib.END: Op.END}
    mask = getattr(lib, "COMMAND_MASK", 0xFF)
    observed = []
    for x, y, command in decoded.stitches:
        basic = command & mask
        if basic not in commands:
            raise ValueError(f"Independent DST decoder emitted unexpected command {basic}")
        observed.append((commands[basic], round(x), round(y)))
    expected = [(e.opcode, e.x10, e.y10) for e in plan.events]
    if observed != expected:
        for index in range(max(len(observed), len(expected))):
            actual = observed[index] if index < len(observed) else None
            planned = expected[index] if index < len(expected) else None
            if actual != planned:
                raise ValueError(
                    f"Independent DST mismatch at event {index}: "
                    f"planned={planned}, decoded={actual} "
                    f"(planned {len(expected)}, decoded {len(observed)})"
                )
    return {"decoder": "pyembroidery", "passed": True,
            "events_compared": len(expected),
            "stitches_compared": sum(e.opcode == Op.STITCH for e in plan.events),
            "jumps_compared": sum(e.opcode == Op.JUMP for e in plan.events)}
