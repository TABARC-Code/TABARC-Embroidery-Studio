"""Versioned .tbes ZIP projects, preserving original assets and object metadata.

Schemas 1 and 2 remain readable and unchanged. Schema 3 saves independent
sewing and reference objects, including exact native cubic control points.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, BadZipFile

from .design import CubicSegment, CurvePath, DesignDocument, EmbroideryObject
from .model import Document, Point, Stroke, StitchSettings

_SCHEMA = 3
_LIMIT = 8_000_000


def _stroke_to_json(stroke: Stroke) -> dict:
    return {'name': stroke.name, 'closed': stroke.closed,
            'points_mm': [[p.x, p.y] for p in stroke.points]}


def _stroke_from_json(raw: dict) -> Stroke:
    if not isinstance(raw, dict) or not isinstance(raw.get('points_mm'), list):
        raise ValueError('Invalid project stroke')
    if len(raw['points_mm']) < 2 or len(raw['points_mm']) > 200000:
        raise ValueError('Invalid stroke point count')
    points = tuple(Point(float(p[0]), float(p[1])) for p in raw['points_mm'])
    if type(raw.get('closed')) is not bool:
        raise ValueError('Stroke closed value must be boolean')
    return Stroke(str(raw['name']), points, raw['closed'])


def _curve_to_json(path: CurvePath) -> dict:
    return {'closed': path.closed,
            'segments': [[[p.x, p.y] for p in (s.p0, s.p1, s.p2, s.p3)] for s in path.segments]}


def _curve_from_json(raw: dict) -> CurvePath:
    if not isinstance(raw, dict) or type(raw.get('closed')) is not bool:
        raise ValueError('Invalid curve path')
    segments = raw.get('segments')
    if not isinstance(segments, list) or len(segments) > 150000:
        raise ValueError('Invalid curve segment count')
    if any(not isinstance(segment, list) or len(segment) != 4 for segment in segments):
        raise ValueError('Cubic segment requires four control points')
    for segment in segments:
        if any(not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float) for v in p)
               for p in segment):
            raise ValueError('Malformed cubic control point')
    return CurvePath(tuple(CubicSegment(*(Point(float(p[0]), float(p[1])) for p in segment))
                           for segment in segments), raw['closed'])


def save_project(doc: Document | DesignDocument, original_svg: bytes) -> bytes:
    if hashlib.sha256(original_svg).hexdigest() != doc.source_sha256:
        raise ValueError('Preserved source asset does not match the document')
    if len(original_svg) > _LIMIT:
        raise ValueError('Source asset exceeds project size limit')
    if isinstance(doc, DesignDocument):
        asset = 'assets/source.' + doc.source_format
        manifest = {
            'schema_version': _SCHEMA, 'units': 'mm',
            'width_mm': doc.width_mm, 'height_mm': doc.height_mm,
            'source_sha256': doc.source_sha256, 'source_asset': asset,
            'geometry_representation': 'per_object_polylines_and_cubics_v1',
            'objects': [{
                'id': obj.object_id, 'name': obj.name, 'kind': obj.kind,
                'thread_hex': obj.thread_hex, 'visible': obj.visible,
                'stitch_settings': asdict(obj.settings),
                'strokes': [_stroke_to_json(s) for s in obj.strokes],
                'curve_paths': [_curve_to_json(p) for p in obj.curve_paths],
                'original_style': obj.original_style,
                'original_parameters': obj.original_parameters,
                'unrendered_features': list(obj.unrendered_features),
            } for obj in doc.objects],
        }
    else:
        asset = 'assets/original.svg'
        manifest = {
            'schema_version': 2, 'units': 'mm',
            'width_mm': doc.width_mm, 'height_mm': doc.height_mm,
            'source_sha256': doc.source_sha256, 'source_asset': asset,
            'geometry_representation': 'flattened_polylines_v1',
            'stitch_settings': asdict(doc.settings),
            'strokes': [_stroke_to_json(s) for s in doc.strokes],
        }
    encoded = json.dumps(manifest, separators=(',', ':'), ensure_ascii=False,
                         allow_nan=False).encode('utf-8')
    if len(encoded) > _LIMIT:
        raise ValueError('Project manifest exceeds size limit')
    with BytesIO() as result:
        with ZipFile(result, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', encoded)
            archive.writestr(asset, original_svg)
        return result.getvalue()


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f'Duplicate manifest key: {key}')
        output[key] = value
    return output


def _bad_constant(value):
    raise ValueError(f'Non-finite project JSON: {value}')


def load_project(data: bytes) -> tuple[Document | DesignDocument, bytes]:
    if len(data) > _LIMIT * 2:
        raise ValueError('Project archive exceeds size limit')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != 2 or len(names) != len(set(names)) or 'manifest.json' not in names:
                raise ValueError('Unexpected project archive structure')
            if any(entry.file_size > _LIMIT or entry.file_size < 0 for entry in entries):
                raise ValueError('Oversized decompressed project member')
            raw_manifest = archive.read('manifest.json')
            manifest = json.loads(raw_manifest.decode('utf-8'), object_pairs_hook=_unique_pairs,
                                  parse_constant=_bad_constant)
            if not isinstance(manifest, dict):
                raise ValueError('Invalid project manifest')
            version = manifest.get('schema_version')
            if type(version) is not int or version not in (1, 2, 3) or manifest.get('units') != 'mm':
                raise ValueError('Unsupported project schema or units')
            asset = ('assets/original.svg' if version < 3 else manifest.get('source_asset'))
            if asset not in ('assets/original.svg', 'assets/source.svg', 'assets/source.ostch'):
                raise ValueError('Untrusted source asset path')
            if set(names) != {'manifest.json', asset}:
                raise ValueError('Unexpected source asset in archive')
            original = archive.read(asset)
    except (BadZipFile, UnicodeError, json.JSONDecodeError, EOFError, RecursionError) as exc:
        raise ValueError('Invalid or damaged .tbes project') from exc
    sha = hashlib.sha256(original).hexdigest()
    if sha != manifest.get('source_sha256'):
        raise ValueError('Preserved source checksum mismatch')
    if version == 3:
        if manifest.get('geometry_representation') != 'per_object_polylines_and_cubics_v1':
            raise ValueError('Unsupported project geometry representation')
        if (asset.endswith('ostch') and manifest.get('source_asset') != 'assets/source.ostch'):
            raise ValueError('Invalid native-source designation')
        raw_objects = manifest['objects']
        if not isinstance(raw_objects, list) or len(raw_objects) > 10000:
            raise ValueError('Invalid object list')
        objects = []
        for item in raw_objects:
            if not isinstance(item, dict):
                raise ValueError('Invalid project object')
            expected = {'id', 'name', 'kind', 'strokes', 'stitch_settings',
                        'thread_hex', 'visible', 'curve_paths', 'original_style',
                        'original_parameters', 'unrendered_features'}
            unexpected = set(item) - expected
            if unexpected:
                raise ValueError(f'Unsupported object attributes: {sorted(unexpected)}')
            curves = tuple(_curve_from_json(p) for p in item.get('curve_paths', []))
            objects.append(EmbroideryObject(
                item['id'], item['name'], item['kind'],
                tuple(_stroke_from_json(s) for s in item['strokes']),
                StitchSettings(**item['stitch_settings']), item['thread_hex'],
                item['visible'], curves, item.get('original_style'),
                item.get('original_parameters', {}),
                tuple(item.get('unrendered_features', ())),
            ))
        doc = DesignDocument(float(manifest['width_mm']), float(manifest['height_mm']),
                             tuple(objects), sha, 'ostch' if asset.endswith('.ostch') else 'svg')
        return doc, original
    if manifest.get('geometry_representation') != 'flattened_polylines_v1':
        raise ValueError('Unsupported geometry representation')
    strokes = tuple(_stroke_from_json(s) for s in manifest['strokes'])
    settings = StitchSettings(**manifest['stitch_settings']) if version == 2 else StitchSettings()
    return Document(float(manifest['width_mm']), float(manifest['height_mm']), strokes, sha, settings), original
