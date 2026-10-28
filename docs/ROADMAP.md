# Development track

## v0.6.0 — available now

Multi-object `.tbes` designs, running/satin/tatami engines, thread colours, DST export, SVG preview and an optional machine-format bridge. This is a pre-alpha command-line build, not a desktop release.

## Next: desktop prototype

1. A PySide6 main window: canvas, hoop, object tree and property panel.
2. Select, move, hide, recolour and reorder objects; changes must survive save/reopen.
3. Preview the composed stitch sequence. Make jumps, trims and colour changes visually distinct.
4. Keep the CLI and document model independent of the GUI so headless export still works.
5. Test on Windows, Linux and macOS. Keep imports safe and complain loudly about unsupported artwork.

## After that: sewability

Add safe underlay, pull compensation, adjustable density, path travel improvements, tie-in/tie-off strategies and a genuine production preflight. Verify each change using saved fixtures, independent decoders and recorded physical sew-outs. Machines don't read changelogs.

## Later: worthwhile extras

Lettering, custom fills, appliqué sequencing, thread chart matching, robust project recovery, and perhaps generative stitch patterns. Look at [RELATED-PROJECTS.md](RELATED-PROJECTS.md) before reinventing a format or algorithm.
