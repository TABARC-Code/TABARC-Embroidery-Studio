# TABARC Embroidery Studio

**Version 0.7.0 · pre-alpha · Windows, macOS and Linux**

An embroidery editor in its early days. The desktop window now handles projects and stitch playback; the proven geometry engine still works behind a command line: I can import a limited set of SVG geometry, lay down running stitches, build a satin column from a pair of rails, fill closed areas with tatami stitches and put differently coloured objects together in a single design.

It is not a finished embroidery programme. The new desktop editor supports object moves and settings but not freehand drawing. The export code also hasn't earned the right to be trusted with expensive fabric. That comes after proper independent testing and a few sacrificial scraps.

## What works

- Import SVG paths, strokes, polygons and supported transforms. Measurements are in millimetres.
- Generate running, two-rail satin and even-odd tatami stitches, including holes.
- Compose independent objects with their own settings, thread colours, visibility and sewing order.
- Keep a design editable in `.tbes` projects (schema 3, with readers for the older two schemas).
- Preview needle movement, inspect a DST file, check hoop bounds and run preflight checks.
- Export Tajima DST without dependencies. Use optional [pyembroidery](https://github.com/EmbroidePy/pyembroidery) for PES, PEC, EXP, JEF, VP3, XXX, U01 and TBF.
- Inspect selected third-party JSON-based project geometry and retain it as non-sewing reference objects. Importing a shape is not the same as reproducing its stitch programme.

`TRIM` and `STOP` exist in the internal event model. The built-in DST writer refuses them rather than making up an equivalent command. The optional exporter has its own format-specific limits.

## Desktop editor

Install the optional Qt interface and open the bundled multi-object design:

```sh
python -m pip install -e '.[desktop]'
tabarc-studio examples/multi-object.tbes
```

There is also `tabarc-embroidery studio examples/multi-object.tbes`. The canvas shows the hoop and its objects; the side panels handle order, visibility, thread colours and stitch settings. You can drag objects, undo edits, preview the needle sequence, save projects and export DST after preflight checks. These are editing tools, not substitutes for a test sew-out.

See [desktop instructions](docs/DESKTOP-WORKFLOW.md) for the actual workflow and restrictions.

## Install

You need **Python 3.10 or newer**. Open a terminal in the repository directory:

```sh
python -m pip install -e .
tabarc-embroidery --version
```

On some Linux and macOS installations, use `python3` instead of `python`. For Windows PowerShell, the same pip command works; use `python -m tabarc_embroidery` if the command-line entry point isn't on your PATH.

For more machine file formats:

```sh
python -m pip install -e '.[formats]'
tabarc-embroidery formats
```

## Try a design

The bundled examples use synthetic artwork made for this project.

```sh
tabarc-embroidery compose \
  examples/multi-object.svg examples/multi-object-assignments.json \
  examples/multi-object.tbes

tabarc-embroidery design-inspect examples/multi-object.tbes

tabarc-embroidery convert \
  examples/multi-object.tbes examples/multi-object.dst \
  --preview examples/multi-object-preview.svg
```

Windows PowerShell: put each command on one line, or use PowerShell's backtick for continuation instead of the backslashes above.

For a straightforward SVG-to-DST conversion:

```sh
tabarc-embroidery convert tests/fixtures/curve.svg examples/curve.dst \
  --preview examples/curve-preview.svg
```

And to test against a separate decoder when the optional library is installed:

```sh
tabarc-embroidery convert tests/fixtures/curve.svg examples/check.dst --independent-check
```

The independent check **fails closed** if that dependency is unavailable. It won't quietly claim to have done the check.

## Working limits

The SVG reader deliberately rejects unsupported geometry: no raster tracing, SVG text, circles, ellipses, clipping masks or elliptical-arc commands yet. Convert those to paths before import. Satin takes two matching open rails; tatami expects suitable closed contours. The stitch engines lack underlay, proper tie-offs, pull compensation and fabric-specific density control.

The generated multi-colour DST was compared with an independent decoder from a separate evidence pack, but that doesn't constitute a real-machine sew-out. Check the results in a separate embroidery viewer and test on scrap fabric first.

## Tests

```sh
python -m pip install -e '.[test]'
python -m pytest -q
python -m compileall -q src
```

CI is configured for Windows, macOS and Linux, with an extra job for pyembroidery. A green local test is not a certificate from an embroidery machine.

## What's next

First: finish the PySide6 workspace with drawing tools and precise object handles. After that: underlay, density warnings, colour routing, useful error messages and a machine-specific validation matrix. I've put the details in [DESCRIPTION.md](DESCRIPTION.md), [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/STATUS.md](docs/STATUS.md).

For the source structure and supported native project data, see [docs/OBJECT-DOCUMENT.md](docs/OBJECT-DOCUMENT.md). The command-line interface lives in `src/tabarc_embroidery/cli.py` and the stitch engines are `running.py`, `satin.py` and `tatami.py`.

## Other embroidery projects worth knowing about

The work didn't happen in a vacuum. These repositories cover similar ground, or solve problems worth studying:

- [pyembroidery](https://github.com/EmbroidePy/pyembroidery) — **MIT**, optional dependency for reading and writing machine formats.
- [libembroidery](https://github.com/Embroidermodder/libembroidery) — **zlib**, C embroidery-file library and a useful second format reference.
- [EmbroideryIO](https://github.com/EmbroidePy/EmbroideryIO) — **MIT**, Java/Android embroidery file I/O.
- [EmbroidePy](https://github.com/EmbroidePy/EmbroidePy) — **MIT**, a wxPython-based viewer/editor project.
- [vpype-embroidery](https://github.com/EmbroidePy/vpype-embroidery) — **MIT**, embroidery/vector processing.
- [Embroidermodder](https://github.com/Embroidermodder/Embroidermodder) — **zlib**, experimental desktop embroidery editor.
- [Ink/Stitch](https://github.com/inkstitch/inkstitch) — **GPL**, mature digitising work and a useful point of comparison.
- [PEmbroider](https://github.com/CreativeInquiry/PEmbroider) — creative coding and procedural stitches; **separate licensing terms apply**.
- [Embroiderly](https://github.com/embroidery-space/embroiderly) — **GPL**, counted cross-stitch rather than general machine digitising.
- [OpenEmbroidery](https://github.com/openembroidery) — hardware control and G-code experiments; licences vary by repository.

More references and the distinction between a dependency and a research source are recorded in [docs/RELATED-PROJECTS.md](docs/RELATED-PROJECTS.md). Links are not claims of code reuse or endorsement.

## Licence

MIT, copyright © 2026 TABARC-Code. See [LICENSE](LICENSE). Optional dependencies retain their own terms; see [LICENSING.md](LICENSING.md). No external project source or third-party design pack is bundled here.
