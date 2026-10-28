# Description · TABARC Embroidery Studio

TABARC Embroidery Studio is my attempt to make a practical embroidery design tool without tying the whole workflow to one machine, one operating system or a pile of proprietary project files.

The end goal is a desktop studio: draw or import artwork, pick the stitch behaviour for each object, watch the needle order and export a file that the machine can actually use. That last bit is the one that matters. A convincing preview is not much comfort if the thread nests under the hoop.

The original command-line engine is still here, alongside the experimental **v0.9.0** desktop editor. It reads a restricted SVG subset, makes running stitches, two-rail satin columns and tatami fills, then combines them into multi-colour, independently configured embroidery objects. Designs can be saved and reopened in the `.tbes` project format. DST is built in; further formats are available through the optional MIT-licensed `pyembroidery` package.

## Working on now

- Extend the PySide6 workbench with Bézier handles, convenient multi-contour selection and clearer warnings for awkward geometry.
- Let me inspect stitch properties without opening JSON files. Sensible defaults will help, but nothing should silently shrink or rewrite a design.
- Playback with needle-up travel, colour changes, problem markers and decent zoom controls.
- Test exported files against independent format readers and real machines. Keep a record of exactly what was tested, including the failures.

## Further down the bench

Underlay, pull compensation, pattern fills, automated routing, thread palettes, lettering, appliqué and a more capable SVG importer. Generative patterns would be fun, though an application that can reliably sew a rectangle comes first.

The code is currently **pre-alpha**. It has passing automated tests, not proven production stitch quality. The project is MIT-licensed, developed under [TABARC-Code](https://github.com/TABARC-Code), and built with a bias towards readable modules rather than an elaborate framework for its own sake.

See [README.md](README.md) for setup, [docs/ROADMAP.md](docs/ROADMAP.md) for staged work, and [docs/RELATED-PROJECTS.md](docs/RELATED-PROJECTS.md) for other open-source embroidery projects worth exploring.

## Desktop workbench (v0.9.0)

A basic Qt workbench now loads editable designs. It provides a hoop canvas, object ordering, thread colours, settings, undo/redo and stitch playback. Grid-snapped vertex handles, open/closed paths and compound fills with holes have landed. Bézier control handles and production-grade diagnostics still need work. The command-line pipeline remains available without Qt.
