"""Needle-order vector preview generated from the same immutable stitch plan."""
from __future__ import annotations
from html import escape
from .model import Op, StitchPlan


def preview_svg(plan: StitchPlan, padding_mm: float = 5.0) -> str:
    events = [e for e in plan.events if e.opcode != Op.END]
    xs = [0] + [e.x10 for e in events]
    ys = [0] + [e.y10 for e in events]
    minx, maxx = min(xs) / 10 - padding_mm, max(xs) / 10 + padding_mm
    miny, maxy = min(ys) / 10 - padding_mm, max(ys) / 10 + padding_mm
    paths = []
    x, y = 0.0, 0.0
    stitches = 0
    current_colour_index = 0
    palette = plan.thread_palette
    colour = palette[0] if palette else '#172a48'
    for e in events:
        nx, ny = e.x10 / 10, e.y10 / 10
        if e.opcode == Op.STITCH:
            paths.append(f'<line x1="{x:.3f}" y1="{y:.3f}" x2="{nx:.3f}" y2="{ny:.3f}" class="stitch" stroke="{colour}"/>')
            stitches += 1
        elif e.opcode == Op.JUMP:
            paths.append(f'<line x1="{x:.3f}" y1="{y:.3f}" x2="{nx:.3f}" y2="{ny:.3f}" class="jump"/>')
        elif e.opcode == Op.COLOUR_CHANGE:
            current_colour_index += 1
            if palette:
                if current_colour_index >= len(palette):
                    raise ValueError('Thread palette is missing a colour segment')
                colour = palette[current_colour_index]
            paths.append(f'<circle cx="{nx:.3f}" cy="{ny:.3f}" r="0.55" class="colour-change"/>')
        elif e.opcode in (Op.STOP, Op.TRIM):
            paths.append(f'<circle cx="{nx:.3f}" cy="{ny:.3f}" r="0.6" class="control"/>')
        x, y = nx, ny
    body = "\n".join(paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{maxx-minx:.3f}mm" height="{maxy-miny:.3f}mm" '
            f'viewBox="{minx:.3f} {miny:.3f} {maxx-minx:.3f} {maxy-miny:.3f}" '
            f'role="img" aria-label="{escape(str(stitches))} needle-down stitches">\n'
            '<style>.stitch{stroke-width:.23;fill:none;stroke-linecap:round}'
            '.jump{stroke:#da654c;stroke-width:.12;stroke-dasharray:1 .6;opacity:.75}'
            '.colour-change{fill:#fff;stroke:#333;stroke-width:.2}'
            '.control{fill:#f6c96b;stroke:#613d19;stroke-width:.15}</style>\n'
            '<rect x="-9999" y="-9999" width="19999" height="19999" fill="#fff"/>\n'
            f'{body}\n</svg>\n')
