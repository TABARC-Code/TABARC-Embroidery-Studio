# Status

**v0.9.0 — pre-alpha (28 October 2026).**

The optional PySide6 workbench supports opening editable designs, selecting and moving objects, thread colour and stitch settings, sewing order, undo/redo, open-polyline running-path drawing, configurable grid snapping, per-path SVG import, node editing with midpoint insertion/deletion, closing/opening running contours and grouping nested closed paths into even-odd fills. Source artwork remains in the `.tbes` archive without being silently rewritten.

The running, two-rail satin and tatami generators, multi-colour stitch composition and built-in DST exporter remain available without the desktop dependency. This is still experimental digitising software, not a verified production system.

Local suite: 123 passed; two optional-dependency tests skipped (PySide6 and pyembroidery). New Qt interaction tests must be checked in GitHub Actions. No physical machine sew-out has been completed. No underlay, pull compensation or reliable tie-offs yet.

See [desktop workflow](DESKTOP-WORKFLOW.md), [roadmap](ROADMAP.md) and [validation](VALIDATION.md).
