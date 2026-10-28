"""Verify user-supplied reconstruction pack without copying included artwork.

Usage:
  python tools/audit_reconstruction_pack.py /path/to/TABARC-Embroidery-Reconstruction-v0.3.0.zip

Output is aggregate metadata only. Package and licence of the underlying designs
remain with their original publisher; no source designs are copied to the app.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from tabarc_embroidery.native_project import inspect_native, load_native_project


def audit(path: Path) -> dict:
    styles = Counter()
    projects = []
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read('public-samples/download-manifest.json'))
        files = manifest['files']
        if len(files) > 5_000 or len(set(x['path'] for x in files)) != len(files):
            raise ValueError('Invalid manifest file list')
        machine_files = 0
        for entry in files:
            # Bundle prefixes here are from the research archive's manifest,
            # not filesystem paths to extract or blindly trust.
            prefix = 'analysis/public-samples/'
            if not entry['path'].startswith(prefix):
                raise ValueError(f'Unexpected sample location: {entry["path"]!r}')
            name = 'public-samples/' + entry['path'][len(prefix):]
            if name not in archive.namelist():
                raise ValueError(f'Missing evidence file: {name}')
            info = archive.getinfo(name)
            if info.file_size != entry['size'] or info.file_size > 16 * 1024 * 1024:
                raise ValueError(f'Size mismatch: {name}')
            raw = archive.read(info)
            if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError(f'Hash mismatch: {name}')
            if name.endswith('.ostch'):
                report = inspect_native(load_native_project(raw))
                projects.append({
                    'source_name': Path(name).name, 'source_sha256': report['source_sha256'],
                    'schema_version': report['version'], 'object_count': report['objects'],
                    'style_counts': report['style_counts'], 'curve_segments': report['curve_segments'],
                    'subpaths': report['subpaths'], 'geometry_empty_objects': report['geometry_empty_objects'],
                    'warnings': report['warnings'],
                })
                styles.update(report['style_counts'])
            elif Path(name).suffix.lower() in ('.dst','.pes','.jef','.vp3','.exp','.xxx','.hus','.tap'):
                machine_files += 1
    return {
        'source_archive': path.name, 'verified_manifest_records': len(files),
        'native_projects': len(projects), 'machine_exports': machine_files,
        'native_objects': sum(p['object_count'] for p in projects),
        'native_style_counts': dict(sorted(styles.items())),
        'projects': sorted(projects, key=lambda x: x['source_name']),
        'limitations': [
            'Only archive record hashes and observed native JSON syntax are checked',
            'No source machine export was regenerated from native artwork',
            'The report does not establish physical sew-out quality or software compatibility',
            'No original design or binary is included in this output',
        ],
    }


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python tools/audit_reconstruction_pack.py RECONSTRUCTION-v0.3.0.zip', file=sys.stderr)
        return 2
    try:
        print(json.dumps(audit(Path(sys.argv[1])), indent=2))
        return 0
    except (KeyError, ValueError, OSError) as exc:
        print(f'Audit failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
