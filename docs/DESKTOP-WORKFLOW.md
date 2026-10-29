# Desktop workspace — v0.10.0

The desktop is an optional part of TABARC Embroidery Studio. The digitising engine and CLI still work without Qt.

## Set up

Python 3.10 or newer is needed. In the project directory:

```sh
python -m pip install -e '.[desktop]'
tabarc-studio examples/multi-object.tbes
```

Or use `tabarc-embroidery studio examples/multi-object.tbes`. On Windows, run these commands in PowerShell. If the executable isn't in PATH, run `python -m tabarc_embroidery studio`.

## A basic design

Open an existing `.tbes` project or an SVG file. SVG import starts with **running stitch** for every imported path; it does not guess whether a silhouette is a fill or a pair of satin rails. Each imported path is now an independent running object. A closed path can be switched to tatami from the object properties, while satin still needs an explicit pair of rails. Ctrl-click multiple closed paths in the object list and use **Edit > Group selected contours as fill** for a compound tatami shape; nested contours become holes under even-odd filling. Overlapping or touching contours are deliberately rejected. Use the `compose` command for more involved stitch assignments.

The left-hand list shows sewing order. Click an object to edit it on the right. Drag its geometry in the centre to move it. You can rename, recolour, hide or reorder objects. Use Ctrl+Z and Ctrl+Shift+Z for undo and redo.

Changes are saved into `.tbes`, leaving the original source artwork and its SHA-256 intact in the archive. The project also preserves original cubic reference curves where present. Saving is atomic: a write goes to a temporary file before replacing the destination.

The **Generate preview** button calculates needle movements from the current document. The lower slider seeks within that movement sequence. A large stitch plan shows only the most recent 3,000 events in the drawing overlay; the position counter makes that limitation explicit. The underlying plan isn't truncated. Orange movement is needle-up travel.

**Export DST** performs basic hoop, stitch-length and DST read-back checks. It blocks known errors rather than silently relaxing settings. The preflight is basic, not proof that a design is ready to sew. Validate files in an independent embroidery viewer and make a supervised test run on scrap fabric.

## Known limits

- You can draw an open running path with **Edit > Draw running path** (D), clicking its points. **Enter** finishes it; **Escape** cancels the pending path; **Backspace** removes the last point. Switch to **Edit > Edit path nodes** (N) to move vertices with the mouse. Right-click a vertex to insert a midpoint after it or remove the vertex. Use **Edit > Close selected contour** or **Open selected contour** to change a running path. The **Active contour** selector chooses a specific ring in compound fills; in node mode only that ring shows draggable vertices. **Edit > Remove selected contour** removes that ring, with undo. The last ring cannot be deleted through this command.
- Reference objects retaining cubic curves now show anchor points and two Bézier controls per segment in node mode. Dragging a shared anchor keeps consecutive segments joined when they originally shared that endpoint. Editing reference curves changes saved reference geometry only; these objects still produce no sewing instructions.
- Use **Snap to grid** in the right-hand panel (Off, 0.5, 1, 2 or 5 mm). Dragging uses the first geometry point as the snap anchor, not the pointer delta. Running paths convert to tatami only when all contours are closed; unsupported conversions are refused.
- Press **F6** or use **View > Inspect design warnings** to populate the diagnostics dock. Click an issue to select its object. This flags out-of-hoop flat vertices, short source edges, very narrow contour bounds, short fill-row spacing, wide satin limits and unsupported DST controls. The panel clears on geometry edits, so you must rerun it to inspect the new result. For terminal users, `tabarc-embroidery design-check design.tbes` prints JSON and exits with code 2 for errors.
- No automatic underlay, pull compensation, colour optimisation, production tie-offs or machine communication.
- No print-ready or machine-certified status. The editor cannot establish thread/fabric suitability from a screen preview.
- Desktop smoke tests run offscreen in CI on Linux. Windows/macOS graphical interaction still needs hands-on testing.

Next practical improvements: full object-to-stitch traceability, event-level markers, better handling of difficult imported shapes and supervised machine sew-outs.
