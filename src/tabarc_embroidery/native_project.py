"""Read-only inspection and vector extraction of observed OSTCH project JSON.

Independent implementation. This reads project geometry, not a finished stitch
compiler. Source artwork is never included or modified by this module.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from html import escape
import json
from math import isfinite
from typing import Any

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 10_000
MAX_SEGMENTS = 150_000
MAX_COORD_MM = 1_000_000
OBSERVED_VERSIONS = frozenset({11, 15})
STYLE_VARIANTS = frozenset({
    'Running', 'Bean', 'Redwork', 'WideRun', 'Zigzag', 'SatinColumn',
    'Fill', 'Applique', 'Manual', 'Guide', 'Decorative',
})


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise ValueError(f'Non-finite JSON numeric constant: {value}')


def _finite_float(value: str) -> float:
    result = float(value)
    if not isfinite(result):
        raise ValueError('Non-finite JSON floating-point value')
    return result


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Cubic control point must be [x, y]')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise ValueError('Non-numeric cubic control point')
    x, y = float(value[0]), float(value[1])
    if not all(isfinite(v) and abs(v) <= MAX_COORD_MM for v in (x, y)):
        raise ValueError('Cubic control point outside finite bounds')
    return x, y


@dataclass(frozen=True)
class Cubic:
    p0: tuple[float, float]
    p1: tuple[float, float]
    p2: tuple[float, float]
    p3: tuple[float, float]


@dataclass(frozen=True)
class NativePath:
    segments: tuple[Cubic, ...]
    closed: bool


@dataclass(frozen=True)
class NativeObject:
    object_id: int
    name: str
    style: str
    style_parameters: dict[str, Any]
    visible: bool
    colour: tuple[int, int, int]
    paths: tuple[NativePath, ...]
    fields: frozenset[str]
    unrendered_features: tuple[str, ...]


@dataclass(frozen=True)
class NativeProject:
    schema_version: int
    objects: tuple[NativeObject, ...]
    source_sha256: str
    hoop: dict[str, Any] | None
    root_fields: tuple[str, ...]
    text_box_count: int
    reference_count: int
    branch_group_count: int


def _segments(item: Any, counter: list[int]) -> tuple[Cubic, ...]:
    if not isinstance(item, list):
        raise ValueError('segments must be an array')
    counter[0] += len(item)
    if counter[0] > MAX_SEGMENTS:
        raise ValueError('Too many native curve segments')
    result = []
    for segment in item:
        if not isinstance(segment, dict):
            raise ValueError('Invalid curve segment')
        result.append(Cubic(*(_point(segment[k]) for k in ('p0', 'p1', 'p2', 'p3'))))
    return tuple(result)


def _colour(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3 or any(
        type(v) is not int or not 0 <= v <= 255 for v in value
    ):
        raise ValueError('Expected RGB thread_color in 0..255')
    return tuple(value)


def load_native_project(data: bytes) -> NativeProject:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('Native project exceeds 16 MiB limit')
    try:
        root = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique_pairs,
                          parse_constant=_bad_constant, parse_float=_finite_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid native-project JSON') from exc
    if not isinstance(root, dict):
        raise ValueError('Native project root must be an object')
    version = root.get('version')
    if type(version) is not int or version not in OBSERVED_VERSIONS:
        raise ValueError(f'Unverified native schema version: {version!r}; observed: 11, 15')
    records = root.get('objects')
    if not isinstance(records, list) or len(records) > MAX_OBJECTS:
        raise ValueError('Invalid or oversized native object array')
    counter = [0]
    objects: list[NativeObject] = []
    seen_ids: set[int] = set()
    for i, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise ValueError(f'Native object #{i} is not an object')
        object_id = raw.get('id')
        if type(object_id) is not int or object_id in seen_ids:
            raise ValueError(f'Invalid/duplicate native object ID at #{i}: {object_id!r}')
        seen_ids.add(object_id)
        style_map = raw.get('stitch_style')
        if isinstance(style_map, str):
            # Serde-style unit variants such as "Guide" and "Manual".
            style, parameters = style_map, {}
        elif isinstance(style_map, dict) and len(style_map) == 1:
            style, parameters = next(iter(style_map.items()))
        else:
            raise ValueError(f'Object {object_id}: expected a stitch_style variant')
        if not isinstance(parameters, dict):
            raise ValueError(f'Object {object_id}: invalid stitch style parameters')
        paths = [NativePath(_segments(raw.get('segments', []), counter),
                            raw.get('closed', False))]
        extras = raw.get('extra_subpaths', [])
        if not isinstance(extras, list):
            raise ValueError(f'Object {object_id}: invalid extra_subpaths')
        for extra in extras:
            if not isinstance(extra, dict):
                raise ValueError(f'Object {object_id}: invalid extra subpath record')
            paths.append(NativePath(_segments(extra.get('segments', []), counter),
                                    extra.get('closed', False)))
        if any(type(path.closed) is not bool for path in paths):
            raise ValueError(f'Object {object_id}: closed flag must be boolean')
        unrendered = []
        for name in ('manual_points', 'shape'):
            if raw.get(name):
                unrendered.append(name)
        if raw.get('meta_nodes'):
            unrendered.append('meta_nodes (not applied to curves)')
        objects.append(NativeObject(
            object_id=object_id,
            name=str(raw.get('name', f'Object {object_id}'))[:512],
            style=str(style), style_parameters=parameters,
            visible=raw.get('visible', True),
            colour=_colour(raw.get('thread_color', [0, 0, 0])),
            paths=tuple(paths), fields=frozenset(raw),
            unrendered_features=tuple(unrendered),
        ))
        if type(objects[-1].visible) is not bool:
            raise ValueError(f'Object {object_id}: visible flag must be boolean')
    def _count(field: str) -> int:
        value = root.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f'{field} must be an array')
        return len(value)
    hoop = root.get('hoop')
    if hoop is not None and not isinstance(hoop, dict):
        raise ValueError('Invalid hoop record')
    return NativeProject(
        schema_version=version, objects=tuple(objects), source_sha256=hashlib.sha256(data).hexdigest(),
        hoop=hoop, root_fields=tuple(root), text_box_count=_count('text_boxes'),
        reference_count=_count('references'), branch_group_count=_count('branch_groups'),
    )


def inspect_native(project: NativeProject) -> dict[str, Any]:
    counts = Counter(obj.style for obj in project.objects)
    all_fields = sorted(set().union(*(obj.fields for obj in project.objects)))
    segments = sum(len(p.segments) for obj in project.objects for p in obj.paths)
    warnings = []
    if project.text_box_count:
        warnings.append('Editable text layout is not interpreted')
    if project.reference_count:
        warnings.append('External reference assets are not rendered')
    if project.branch_group_count:
        warnings.append('Branch groups and hidden travel are not regenerated')
    if any(o.unrendered_features for o in project.objects):
        warnings.append('Some native object features are omitted in geometry-only SVG')
    unknown_styles = sorted(set(counts) - STYLE_VARIANTS)
    if unknown_styles:
        warnings.append('Unrecognised stitch styles: ' + ', '.join(unknown_styles))
    return {
        'format': 'OSTCH JSON (observed subset)', 'version': project.schema_version,
        'source_sha256': project.source_sha256, 'objects': len(project.objects),
        'style_counts': dict(sorted(counts.items())), 'curve_segments': segments,
        'subpaths': sum(len(o.paths) for o in project.objects),
        'geometry_empty_objects': sum(not any(p.segments for p in o.paths) for o in project.objects),
        'object_fields_observed': all_fields,
        'root_fields': list(project.root_fields),
        'hoop': project.hoop,
        'text_boxes': project.text_box_count, 'references': project.reference_count,
        'branch_groups': project.branch_group_count,
        'geometry_only_export': True, 'not_a_stitch_reconstruction': True,
        'warnings': warnings,
    }


def native_geometry_svg(project: NativeProject, *, include_hidden: bool = False,
                        selected_ids: set[int] | None = None) -> str:
    """Export original cubic geometry only; stitches, density and trims NOT reproduced."""
    if selected_ids is not None:
        unknown = selected_ids - {o.object_id for o in project.objects}
        if unknown:
            raise ValueError(f'Unknown native object IDs: {sorted(unknown)}')
    used = [o for o in project.objects if (include_hidden or o.visible)
            and (selected_ids is None or o.object_id in selected_ids)]
    points = [p for obj in used for path in obj.paths for seg in path.segments
              for p in (seg.p0, seg.p1, seg.p2, seg.p3)]
    if not points:
        raise ValueError('No visible cubic geometry to export; manual point arrays are not SVG paths')
    minx, maxx = min(p[0] for p in points), max(p[0] for p in points)
    miny, maxy = min(p[1] for p in points), max(p[1] for p in points)
    padding = 2.0
    minx, miny = minx - padding, miny - padding
    width, height = max(0.1, maxx - minx + padding), max(0.1, maxy - miny + padding)
    paths_xml = []
    for obj in used:
        commands = []
        for path in obj.paths:
            if not path.segments:
                continue
            # Native paths may contain more than one disconnected sequence.
            previous = None
            for seg in path.segments:
                if previous is None or abs(previous[0] - seg.p0[0]) + abs(previous[1] - seg.p0[1]) > 1e-5:
                    commands.append(f'M {seg.p0[0]:.6f} {seg.p0[1]:.6f}')
                commands.append('C ' + ' '.join(f'{p[0]:.6f} {p[1]:.6f}'
                                               for p in (seg.p1, seg.p2, seg.p3)))
                previous = seg.p3
            if path.closed:
                commands.append('Z')
        if not commands:
            continue
        rgb = '#%02x%02x%02x' % obj.colour
        paths_xml.append(f'<path id="native-{obj.object_id}" data-native-style="{escape(obj.style, quote=True)}" '
                         f'data-native-name="{escape(obj.name, quote=True)}" d="{escape(" ".join(commands), quote=True)}" '
                         f'fill="none" stroke="{rgb}" stroke-width="0.2"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}mm" height="{height:.3f}mm" '
            f'viewBox="{minx:.3f} {miny:.3f} {width:.3f} {height:.3f}">\n'
            '<!-- Geometry preview only: not native stitch reconstruction or machine output. -->\n'
            + '\n'.join(paths_xml) + '\n</svg>\n')
