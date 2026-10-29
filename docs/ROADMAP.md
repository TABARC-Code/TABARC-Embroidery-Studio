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

## v0.8.0 — precision editing (implemented)

- A grid selector (off/0.5/1/2/5 mm) with absolute object-anchor snapping.
- Expanded selection hit area for narrow paths, and deferred Qt scene rebuilding after drag.
- Draw open running paths on the hoop (Enter to finish, Escape to cancel); save them as proper objects.
- Import SVG strokes as independently editable running objects, rather than bundling everything into one.
- Explicit running/tatami conversion for closed paths. No invented satin rails.
- Core regression tests for geometry, snap rounding, project saving and undo. Qt interaction tests run in CI.

## v0.9.0 — precision nodes and compound contours (implemented)

- Node handles in the Qt canvas, with grid-aware movement and a right-click insert/delete menu.
- Open and close flattened running paths; convert to tatami only when the fill is valid.
- Group separate closed contours as an even-odd tatami object. Nested contours remain holes, and crossing/touching rings fail validation.
- Save and reopen edits in the existing schema-3 project without changing the original artwork.
- Add model-level regression tests and Qt offscreen coverage.

## v0.10.0 — geometry tools and diagnostics (implemented)

- Select a contour inside a compound fill; edit its vertices or remove the contour with undo/redo.
- Edit original cubic anchors and control points on reference objects without flattening or inventing stitches. Shared endpoints move together when originally coincident.
- Add object-level diagnostic messages for geometry outside the hoop, tiny source edges, narrow fill bounds and suspect settings. Surface them in a dock and via `design-check` JSON output.
- Preserve schema-3 project compatibility and the CLI pipeline. Desktop interaction tests belong in the Qt CI job.

## v0.11.0 — after verification

- Report generated needle events against their source object, including jumps between objects and colour changes.
- Extend live simulation with warnings tied to actual stitch positions.
- Improve automated tests for compound fills and saved cubic reference artwork.
- Record supervised machine sew-outs before recommending production settings. An SVG preview isn't proof of anything stitched.
