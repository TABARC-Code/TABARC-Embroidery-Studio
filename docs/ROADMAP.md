# Development track

## v0.6.0 — available now

Multi-object `.tbes` designs, running/satin/tatami engines, thread colours, DST export, SVG preview and an optional machine-format bridge. This is a pre-alpha command-line build, not a desktop release.

## v0.7.0 — desktop workbench (implemented)

1. A PySide6 main window with a canvas, hoop, object list and properties.
2. Select, move, hide, recolour and reorder objects; changes survive save/reopen with undo/redo.
3. Preview the composed stitch sequence. Make jumps, trims and colour changes visually distinct.
4. Keep the CLI and document model independent of the GUI so headless export still works.
5. Test on Windows, Linux and macOS. Keep imports safe and complain loudly about unsupported artwork.

## After that: sewability

Add safe underlay, pull compensation, adjustable density, path travel improvements, tie-in/tie-off strategies and a genuine production preflight. Verify each change using saved fixtures, independent decoders and recorded physical sew-outs. Machines don't read changelogs.

## Later: worthwhile extras

Lettering, custom fills, appliqué sequencing, thread chart matching, robust project recovery, and perhaps generative stitch patterns. Look at [RELATED-PROJECTS.md](RELATED-PROJECTS.md) before reinventing a format or algorithm.

## Next: precision tools

Add explicit object creation and SVG assignment, snapping and handles, object-level stitch preflight, and full UI integration tests on the supported systems. Keep the first physical sew-out separate from UI progress.
