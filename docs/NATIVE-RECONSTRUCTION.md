# Native OSTCH compatibility — v0.5.0

The separately supplied reconstruction archive contains four third-party embroidery software `.ostch` projects. Their original bytes matched the 34-entry download manifest. They use observed schema versions **11** and **15**, represent **63 native objects**, and include paired embroidery-machine exports. A format-level match does not establish stitch-output equivalence.

## Implemented

A new read-only `native_project.py` recognises the observed JSON project structure. It parses per-object IDs, names, visibility, colours, style names and settings, cubic Bézier segments and additional subpaths. It accepts both tagged style maps (`{"Running":{...}}`) and unit strings (`"Guide"`, `"Manual"`), as seen in the examples. The parser limits input size and object/segment counts and rejects duplicate keys, bad object IDs, non-finite coordinates and unsupported schema versions.

`native-inspect` reports project properties, style counts and omitted features. `native-svg` exports the native cubic paths, with visibility and object-ID filters. The result is editable **geometry only**, not a reconstruction of native stitches. No machine output is produced from OSTCH input.

```
python -m tabarc_embroidery native-inspect input.ostch
python -m tabarc_embroidery native-svg input.ostch geometry.svg
python -m tabarc_embroidery native-svg input.ostch selected.svg --object-id 7
python -m tabarc_embroidery native-svg input.ostch all.svg --include-hidden
```

The original research archive may be audited without extracting its contents:

```
PYTHONPATH=src python tools/audit_reconstruction_pack.py /path/to/TABARC-Embroidery-Reconstruction-v0.3.0.zip
```

The generated `docs/NATIVE-CORPUS-VALIDATION.json` contains aggregate verification results only. No original designs, fonts, commercial patterns or native project files are bundled. The public availability of examples does not grant a blanket redistribution licence. No recovered proprietary implementation is copied.

## Limits and priorities

The reader does not reproduce satin crossings, zigzag widths, tatami patterns, appliqué operator pauses, underlay, tie-offs, trims, branch routing, manual needle-point placement or text/font regeneration. Some objects have no cubic geometry. The original `.ostch` file is not written back; a faithful native round trip is not established.

Next: implement a typed multi-object TABARC document model, preserve raw style metadata and separate visual curves from embroidery semantics; introduce explicit STOP/TRIM/COLOUR_CHANGE commands; add controlled minimal examples for geometry-to-stitch calibration; verify selected outputs with independent pyembroidery and physical machine tests; then build the GUI on top of the validated model.
