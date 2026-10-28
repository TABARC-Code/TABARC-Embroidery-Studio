# v0.6.0 object model and machine-event semantics

## Design and source fidelity

A `DesignDocument` contains ordered `EmbroideryObject` entries. Their immutable
sewing configuration is scoped per object rather than per SVG. Source geometry
and stitch generation are **distinct**: `strokes` contain sampled mm polylines
used for planned stitches, while `curve_paths` contain original cubic control
points retained as geometry references. Original `.svg` or `.ostch` bytes are
embedded in schema-3 `.tbes` alongside a mandatory SHA-256 digest.

Kinds:

- `running`: one or more open/closed polylines, resampled into needle points.
- `satin`: two open rail paths; no automatic rail inference.
- `tatami`: closed contours with even-odd hole rules.
- `reference`: non-sewing artwork/metadata; never silently digitised.
- `colour_change`: explicit thread-segment transition at current position.
- `trim`: distinct machine TRIM event, no movement.
- `stop`: operator STOP event, no movement; not a colour change.

`visible: false` excludes that object from the resulting stitch plan. Only
explicit supported geometry can be digitised. If a `.ostch` is adapted,
**every object initially becomes `reference`**, including original satin and
fill objects. Original parameters and native style strings are retained for
future work, not assumed correct for our generators.

A separate opt-in `design-promote-running` command takes a native Running
reference and samples its observed Bézier geometry to the existing TABARC
running-stitch engine. It refuses unknown Running settings and unrendered
native features. It does **not** reproduce proprietary stitch output.

## Sewing sequence

`generate_design_plan` produces an immutable `StitchPlan` with absolute
0.1 mm needle locations. It combines each object's existing tested stitch
engine, but removes only its *leading* origin-to-start jumps and replaces
those with bounded jumps from the current live needle position. Intra-object
jumps and stitches remain unchanged. Changes between different thread colours
produce `COLOUR_CHANGE`, unless the document explicitly requests additional
colour stops. The plan records an ordered `thread_palette`.

- `COLOUR_CHANGE`: supported in native DST and optional format bridge.
- `TRIM`: retained internally. Native DST refuses export rather than emit
  an ambiguous sequence. Optional pyembroidery uses its `TRIM` command if
  that installed backend exposes it; results still need machine testing.
- `STOP`: retained internally and **not exported** in any backend. Mapping
  this to a colour change would alter the explicit operator instruction.
- No automatic trims, underlay, thread-locks or routing optimisation.

Preflight checks occupied extents and stitch lengths before writing the file.
The current hoop assumes top-left source registration, not calibrated machine
origin. A passing preflight report does not establish production safety.

## Reproducible checks and limits

Run `PYTHONPATH=src python -m pytest -q`. The new tests include mixed stitch
styles, same/different-colour transitions, no needle-down between objects,
visible/reference behaviour, explicit STOP/TRIM, invalid inputs, schema 3
save/open, backwards compatibility and synthetic native source preservation.

The separate **user-provided** `dst_probe.py` in the reconstruction evidence
pack decoded the example `examples/multi-object.dst`: 185 of 185 command/point
records matched the internal decoder. This checks one generated file against a
second independent implementation; the actual pyembroidery package could not
be installed locally. The decoder used by CI's optional job may be different.

`tools/validate_native_adapter.py <path-to-reconstruction.zip>` validates the
four original `.ostch` source samples without extracting or packaging publisher
assets. Verified: 4 sources, 63 objects, unchanged source hashes, preserved
original object names/styles/colours/cubics, zero implicit native sewing.

No source sample stitches were reproduced or compared on a machine. No
vendor copyrighted artwork or machine-format exports are redistributed in
this source package.
