# Status

**v0.10.0 — pre-alpha (29 October 2026).**

The optional PySide6 workbench supports opening editable designs, selecting and moving objects, thread colour and stitch settings, sewing order, undo/redo, open-polyline running-path drawing, configurable grid snapping, per-path SVG import, node editing with midpoint insertion/deletion, per-contour selection/removal, closing/opening running contours, grouping nested closed paths into even-odd fills, and control-point editing for retained non-sewing cubic reference paths. Source artwork remains in the `.tbes` archive without being silently rewritten.

The running, two-rail satin and tatami generators, multi-colour stitch composition and built-in DST exporter remain available without the desktop dependency. This is still experimental digitising software, not a verified production system.

Local suite: 130 passed; two optional-dependency tests skipped (PySide6 and pyembroidery). Desktop interaction tests require GitHub Actions verification. Object-level design checks report geometry and settings warnings, but are not physical sewability tests. No physical machine sew-out has been completed. No underlay, pull compensation or reliable tie-offs yet.

See [desktop workflow](DESKTOP-WORKFLOW.md), [roadmap](ROADMAP.md) and [validation](VALIDATION.md).
