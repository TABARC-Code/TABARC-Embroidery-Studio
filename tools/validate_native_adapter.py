"""Validate schema-3 preservation against an *external* reconstruction archive.

Usage: python tools/validate_native_adapter.py /path/to/reconstruction-v0.3.0.zip
No third-party designs are copied into the repository or output files.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from sys import argv
from zipfile import ZipFile
import json

from tabarc_embroidery.native_project import load_native_project
from tabarc_embroidery.design import design_from_native, generate_design_plan
from tabarc_embroidery.project import load_project, save_project


def audit(archive_path: Path) -> dict:
    counts = Counter()
    checked = []
    with ZipFile(archive_path) as archive:
        names = [name for name in archive.namelist()
                 if name.startswith('public-samples/') and name.endswith('.ostch')]
        if not names:
            raise ValueError('No native source samples found in archive')
        for name in sorted(names):
            contents = archive.read(name)
            original = load_native_project(contents)
            adapted = design_from_native(original)
            restored, original_bytes = load_project(save_project(adapted, contents))
            if original_bytes != contents or restored != adapted:
                raise ValueError(f'Native reference round-trip mismatch: {name}')
            if any(obj.kind != 'reference' for obj in restored.objects):
                raise ValueError(f'Native reference silently promoted to machine sewing: {name}')
            try:
                generate_design_plan(restored)
            except ValueError as exc:
                if 'no stitchable visible objects' not in str(exc):
                    raise
            else:
                raise ValueError(f'Native-only project unexpectedly stitched: {name}')
            counts.update(obj.original_style for obj in restored.objects)
            checked.append({'file': name, 'sha256': restored.source_sha256,
                            'objects': len(restored.objects),
                            'curves': sum(len(path.segments) for obj in restored.objects
                                          for path in obj.curve_paths)})
    return {'source_archive': archive_path.name, 'native_projects': len(checked),
            'objects': sum(row['objects'] for row in checked),
            'source_style_counts': dict(sorted(counts.items())),
            'round_trip_verified': True, 'native_stitches_recreated': False,
            'source_files': checked}


if __name__ == '__main__':
    if len(argv) != 2:
        raise SystemExit('Usage: PYTHONPATH=src python tools/validate_native_adapter.py archive.zip')
    print(json.dumps(audit(Path(argv[1])), indent=2))
