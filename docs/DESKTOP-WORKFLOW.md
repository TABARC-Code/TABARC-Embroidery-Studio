# Desktop workspace — v0.7.0

The desktop is an optional part of TABARC Embroidery Studio. The digitising engine and CLI still work without Qt.

## Set up

Python 3.10 or newer is needed. In the project directory:

```sh
python -m pip install -e '.[desktop]'
tabarc-studio examples/multi-object.tbes
```

Or use `tabarc-embroidery studio examples/multi-object.tbes`. On Windows, run these commands in PowerShell. If the executable isn't in PATH, run `python -m tabarc_embroidery studio`.

## A basic design

Open an existing `.tbes` project or an SVG file. SVG import starts with **running stitch** for every imported path; it does not guess whether a silhouette is a fill or a pair of satin rails. Use the `compose` command to assign different stitch styles to SVG paths until the desktop provides a proper object import wizard.

The left-hand list shows sewing order. Click an object to edit it on the right. Drag its geometry in the centre to move it. You can rename, recolour, hide or reorder objects. Use Ctrl+Z and Ctrl+Shift+Z for undo and redo.

Changes are saved into `.tbes`, leaving the original source artwork and its SHA-256 intact in the archive. The project also preserves original cubic reference curves where present. Saving is atomic: a write goes to a temporary file before replacing the destination.

The **Generate preview** button calculates needle movements from the current document. The lower slider seeks within that movement sequence. A large stitch plan shows only the most recent 3,000 events in the drawing overlay; the position counter makes that limitation explicit. The underlying plan isn't truncated. Orange movement is needle-up travel.

**Export DST** performs basic hoop, stitch-length and DST read-back checks. It blocks known errors rather than silently relaxing settings. The preflight is basic, not proof that a design is ready to sew. Validate files in an independent embroidery viewer and make a supervised test run on scrap fabric.

## Known limits

- No on-canvas drawing or SVG text editing yet. Import only the limited SVG geometry supported by the existing parser.
- Stitch type changes aren't guessed from geometry. The workspace edits the type assigned in the project, not the underlying shape topology.
- No automatic underlay, pull compensation, colour optimisation, production tie-offs or machine communication.
- No print-ready or machine-certified status. The editor cannot establish thread/fabric suitability from a screen preview.
- Desktop smoke tests run offscreen in CI on Linux. Windows/macOS graphical interaction still needs hands-on testing.

Next practical improvements: selected-object handles, on-canvas shape creation, a proper SVG assignment dialogue and warnings tied to the chosen machine/hoop.
