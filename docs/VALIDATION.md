# DST validation protocol

**Status: external reader and physical machine NOT YET VALIDATED.** This is a reproducible checklist, not proof of completion.

## Source material

The DST coordinate convention and bit assignments were checked against the pyembroidery reader:
https://github.com/EmbroidePy/pyembroidery/blob/main/pyembroidery/DstReader.py

That reader explicitly negates raw DST Y displacement to obtain graphics-style coordinates. Our exporter now negates graphics Y during encoding, and our structural decoder reverses the transform. Tests also assert known literal records, independently of our own encoder output.

## Required checks (not performed)

1. Create fresh `curve.dst`, `straight.dst`, `satin.dst`, and `fill-with-hole.dst` with v0.3.0. Record checksum, number of needle-down records, jump records, last needle point and bounding box.
2. Read each with the installed `pyembroidery` package (record version), preserving raw jumps where possible. Compare coordinates to the `.tbes` / generated plan, allowing only the documented 0.1 mm integer grid precision.
3. Open in an independent visual embroidery viewer, specifically check top/bottom orientation against SVG source, and inspect no sewn lines across the hole.
4. Confirm machine profile, usable hoop dimensions, origin offsets, thread/fabric, stitch density, needle compatibility and physical safe positioning before controlled sew-out.
5. Supervise short test patterns, then satin and simple fill. Log broken threads, puckering, skips, unsuitable underlay, excessive jumps and corrections.
6. Save test machine model, firmware, viewing software, thread, fabric, backing and photos with test results.

Do not infer that an internally round-tripping DST file is machine-ready. v0.2.0 files contained a Y-axis error and must be regenerated.

## v0.4.0 additions

The new `--independent-check` flag delegates the DST decoding to installed pyembroidery and compares every source event. This comparison is **not complete** until it has actually run against that package. A dedicated GitHub Actions job is configured to install `[formats]` and test it, but no remote run has been observed. The local package tests only a mock external API.

Generated PES/PEC/EXP/JEF/VP3/XXX/U01/TBF files, when produced with the optional dependency, must be independently reopened and given supervised sew-outs before anyone relies on them.
