# Status

**v0.8.0 — pre-alpha (28 October 2026).**

The optional PySide6 workbench supports opening editable designs, selecting and moving objects, thread colour and stitch settings, sewing order, undo/redo, open-polyline running-path drawing, configurable grid snapping, per-path SVG import and deliberate running/tatami conversion for closed contours. Source artwork remains in the `.tbes` archive without being silently rewritten.

The running, two-rail satin and tatami generators, multi-colour stitch composition and built-in DST exporter remain available without the desktop dependency. This is still experimental digitising software, not a verified production system.

Local suite: 118 passed; two optional-dependency tests skipped (PySide6 and pyembroidery). The updated desktop smoke tests must be checked separately in GitHub Actions. No physical machine sew-out has been completed. No underlay, pull compensation or reliable tie-offs yet.

See [desktop workflow](DESKTOP-WORKFLOW.md), [roadmap](ROADMAP.md) and [validation](VALIDATION.md).
