# TABARC Embroidery Studio
## Product and development plan, v0.1
**Status:** original plan, Phase 1 prototype in progress (see STATUS.md)  
**Owner:** TABARC-Code  
**Date:** 27 October 2026  
**Working title:** TABARC Embroidery Studio (provisional)

## 1. Purpose
Build a desktop, offline-first embroidery digitising and production application for hobbyists, makers and small creative businesses. It must let a designer take existing raster or vector artwork, define stitch intent, simulate the resulting stitch sequence, and export machine-readable embroidery files. Its editable native project must remain separate from the machine-stitch output.

third-party embroidery software is a useful feature benchmark, **not** an available codebase or a specification to copy. Build an independent interface and algorithms. No assumption of third-party embroidery software source availability.

### Design principles
1. Reliable stitch geometry and machine-safe output before visual polish.
2. Artwork stays editable: size changes regenerate stitches from source geometry.
3. Manual control first, automation as an editable assistant.
4. Offline-first, no accounts required to design and export.
5. Cross-platform architecture, with support and tests delivered progressively.
6. Every exported format is tested independently; feature lists are not verification.
7. Accessible UI: keyboard, configurable contrast and predictable shortcuts.
8. Modular construction for embroidery, quilting, patches and production workflows.

## 2. Audience and workflows
**Primary:** small embroidery / textile maker using desktop graphics and a single- or multi-needle embroidery machine.  
**Secondary:** graphic designers preparing client logos, patches and lettering; workshops teaching embroidery; makers who need batch exports.

**Workflow A, logo to patch:** SVG/PNG import > scale and select hoop > assign paths and thread colours > running/satin/fill > preview > inspect warnings > save project > PES/DST export > production worksheet > sew-out check.

**Workflow B, editing a stitch file:** PES/DST import > stitch-sequence visualisation > safe reordering/trims/colour mapping where supported > export. Imported machine-stitch data is not falsely advertised as recovered vector objects.

**Workflow C, batch work (later):** open an editable master > create size/hoop variants > rerender density-aware > test constraints > export approved formats to named folders.

## 3. Scope: first public release
### P0, engine and minimum useful designer
- Native editable `.tbes` project: versioned JSON manifest plus artwork/assets inside ZIP container.
- Single document workspace; millimetres as canonical geometry unit.
- Layer/object model: vector path, polygon, reference image, stitch object, colour and machine order.
- Basic SVG import (paths and shapes with transforms); raster reference PNG/JPEG import.
- Selection, pen / Bezier editing, straight paths, shape primitives, transforms, undo/redo, pan/zoom, grid and snapping.
- Configurable hoop and printable design extent, including margins and out-of-bounds warnings.
- Running stitch generation on centreline with configurable stitch length and corner handling.
- Satin generator for uncomplicated two-rail columns, with adjustable direction; warning on unsupported geometry.
- Tatami / parallel fill over closed polygon outlines (including holes) with density and angle controls.
- Thread palette with editable colour labels and a generic thread list.
- Explicit order of operations: sew order, jumps, colour changes, optional tie-in/out, trims and stops.
- 2D thread preview and **needle-order** stitch playback; no claim to full fabric physics.
- Format import/export through an adapter layer, initially DST and PES.
- Export preflight: hoop bounds, zero or extreme stitch length, oversized jumps, unsupported commands and preview mismatch.
- Autosave, crash recovery, manual project save and a reproducible test suite.

### P1, useful production release
- Editable lettering via path conversion and basic font-to-stitch parameters.
- Improved satin rails/rungs, direction control, corner mitigation and wide-column split strategies.
- Underlay types (centre, edge/contour, zigzag and fill underlay), compensation presets.
- Colour-change minimisation under preserved layer/dependency constraints.
- JEF, EXP and VP3 export, subject to format-specific validation.
- Production worksheet: colours, stitch count, design size, hoop, trims/stops, machine file and notes.
- Parameter presets by fabric and stabiliser, explicitly labelled as starting points, not guarantees.
- More generous path editing, copy/paste, alignment and boolean polygon operations.
- First-run tutorial and accessible customisable shortcuts.

### P2, planned extensions
- Image segmentation, colour reduction, vector tracing and guided auto-digitisation.
- Appliqué placement/tack-down/cut/cover sequences.
- Decorative repeats, redwork continuous-line routing, custom fills and motifs.
- Multi-format batch exports, design library and metadata tagging.
- More output formats where tested (HUS, XXX, TAP etc.).
- QR/pixel embroidery generation with minimum-size and legibility checks.
- Advanced font creation and monogram templates.
- Density heatmaps, configurable fabric distortion heuristic, estimated production time and thread usage.
- Optional plugin API, command-line batch mode and automation integrations.

### Explicitly not in MVP
- Generative AI or fully automatic production-grade digitisation.
- A physically accurate simulation of fabric deformation.
- Direct USB/network hardware control (requires separate research and safety testing).
- Unverified claims of universal machine compatibility.
- Cloud accounts, marketplace or subscription system.

## 4. Architecture
```
Desktop UI (PySide6 / Qt)
  |-- document, layers, selection, tools, undo/redo
  |-- thread/hoop/production panels
  |-- stitch preview and playback
  v
Application services
  |-- command bus / state history / autosave
  |-- validators, warnings, project storage
  |-- asset importers, machine profiles, worksheet
  v
Editable design model [canonical mm coordinates]
  |-- path geometry, groups, transforms
  |-- stitch intent + parameters per design object
  |-- stitch order constraints, colour palette, hoop
  v
Geometry/stitch engine [pure testable functions]
  |-- path flattening / arcs / interpolation
  |-- run generator / satin generator / tatami generator
  |-- underlay, routing, ties, jumps, trims
  v
Immutable stitch sequence [needle positions + commands]
  |-- simulation renderer and inspection
  |-- production/preflight validation
  |-- export adapters (pyembroidery first)
  v
Machine format outputs [PES, DST first]
```

### Technology recommendation
- **Python 3.12+** for orchestration, algorithms and fast early development, pinned and tested against supported interpreters.
- **PySide6 / Qt 6** for desktop UI and hardware-accelerated-capable canvas infrastructure. Start with a custom QGraphicsView/QPainter approach, avoiding one scene item per stitch at high stitch counts.
- **pyembroidery** (MIT) as a candidate I/O backend for machine-file codecs; it does **not** generate high-level stitch geometry and must not be mistaken for the digitiser.
- **Shapely/GEOS** for polygon operations and intersection tests, after assessing packaging, licence and topology failure modes. Geometry helpers behind an interface, not strewn through the UI.
- **pytest, hypothesis, ruff, mypy** for static validation and property-based testing.
- **GitHub Actions** for multi-OS tests, artefact builds and release signing strategy.
- Optional native geometry backend only after profiling exposes a real bottleneck; no premature Rust/C++ rewrite.

### Licence and compliance note
third-party embroidery software is proprietary; treat public information as requirements research, not code. Ink/Stitch is GPL-3.0; don't copy its implementation into a differently licensed proprietary product. pyembroidery is MIT-licensed. libembroidery is zlib-licensed but is documented as alpha, so evaluate it as a reference or secondary adapter rather than relying on it for first release. PySide6 is available under LGPL/GPL/commercial terms; check distribution obligations and use of any Qt add-ons before selecting the product licence. Include attributions and licence files as required.

## 5. Data model and invariants
**DesignDocument:** schema_version, id, created_at, units="mm", hoop_id, dimensions_mm, source_assets, layer_ids, palette, stitch_plan, project_settings.

**DesignObject:** id, type, transform, geometry, colour_ref, stitch_style, parameters, visibility, locked, order_constraints.

**StitchPlan:** ordered `StitchEvent`s, generator_version, source_document_hash, deterministic seed, warnings.

**StitchEvent:** position_mm (nullable for state-only commands), opcode (STITCH, JUMP, TRIM, STOP, COLOUR_CHANGE, END), thread_ref, source_object_id.

**MachineProfile:** format, design_bounds_mm, needle count, supported commands, colour-change semantics, optional machine-specific limits; distinguish authoritative values from user-supplied settings.

### Invariants
- Canonical stored dimensions are mm, not pixels; SVG user units need explicit conversion.
- Colour order, jump/trims and stitch positions cannot change unpredictably between preview and export.
- Rendering does not mutate the editable document; stitch-generation functions are deterministic for a fixed version and inputs.
- Resizing editable geometry reruns stitch generation at the target size. Resizing imported stitch-only designs requires warnings.
- A machine export is a derivative, not the source of truth.
- Failure or invalid design reports a specific error; no silently incomplete file.

## 6. Algorithms: expected first implementation
### Running stitch
Flatten curves to a specified error tolerance in millimetres. Resample by arc length with safeguards for tiny segments, corners and maximum stitch distance. Allow reverse direction and endpoints. Write geometry-based unit tests and pathological shape tests.

### Satin stitch
Model a satin as two rails with matched cross-sections/rungs. Sample along one travel direction and alternate rail endpoints. Reject or warn on self-intersections, ambiguous rails, sharp corners and excessive width. Add underlay and pull compensation after the baseline algorithm is tested. Do not promise a universal conversion from arbitrary outlines to satin.

### Tatami fill
Clip a set of parallel scanlines to a valid polygon including holes; traverse rows in a controlled alternating order with configurable stitch length, spacing, fill angle and offset. Ensure holes and disjoint intersections never get stitched by a straight cross-over by accident. Plan travel stitches explicitly.

### Routing
Build order constraints first (underlay before top stitch, appliqué placement before cover, layer/overlap dependencies). Optimise entry/exit and colour groups only within valid constraints. Never shorten travel by changing visible over/under composition.

### Preflight
Check dimensions/hoop placement, zero-area paths, tiny features, degenerate geometry, low/high stitch length, repeated zero moves, density extremes, unsupported colour changes, jump distances, non-finite coordinates, forbidden/out-of-range instructions and format capability mismatches. Warning thresholds must be configurable and machine-profile-specific where applicable.

## 7. UX concept
Desktop workspace with a left vertical drawing toolbar, central zoomable workspace with hoop overlay, right tabs for object properties / stitching / threads / machine settings and bottom panels for sequence timeline and problem list. A toggle switches between **Artwork**, **Needle Preview**, and **Playback** without leaving the workspace. Preflight problems are linked to the offending object / stitch number. No hidden modal dialogs for basic density and direction changes.

Use drawing-app conventions where sensible; retain conventional keyboard shortcuts and remember panel layouts. Avoid dependence on colour alone for status. Build a small suite of keyboard-only workflows before expanding feature breadth.

## 8. Stage gates and acceptance criteria
**S0, research and feasibility**
- Document five representative machine exports and target-machine capabilities, with actual sample files for regression.
- Verify pyembroidery handling of PES/DST read/write and all required commands.
- Establish a licence inventory and physical-test partner/machine list.
- Create UI and engine proof-of-concepts separately.

**S1, stitch-engine prototype**
- SVG path > running stitches > DST file successfully opens in at least one independent viewer.
- A 2-rail satin and a polygon-with-hole fill each render correctly and produce deterministic tests.
- Exported commands and preview originate from exactly the same generated StitchPlan.
- Store engine fixtures for a line, curve, rectangle, donut/hole, overlapping objects and multicolour sample.

**S2, editor alpha**
- Open an SVG, set hoop, select paths, assign stitches/threads, save, reopen and edit without loss.
- Undo/redo covers all document-changing commands; autosave and restore tested.
- Preview and DST/PES exports pass round-trip structural checks; document any lossy conversion.

**S3, real-machine beta**
- Run physical sew-outs for run, satin, fill, outline lettering, multicolour patch and boundary cases on known fabric/stabiliser/machine combinations.
- Record measured geometry, pulling/gaps, thread breaks, trims, machine rejection and actual stitch time.
- Each supported export format has fixture tests and at least one validated target-machine path, with compatibility notes where necessary.

**S4, public v1.0**
- Two independently validated machine-output formats minimum, no open critical export or data-loss bugs, cross-platform smoke tests on advertised OS builds, beginner tutorial, documented limitations, recovery workflow and transparent release notes.

## 9. Test strategy
- Golden geometry tests: deterministic stitch sequences; assert no NaN/infinity, minimum/maximum limits, hole preservation.
- Property tests: translations, rotation, scale and object-order constraints; geometry topology cases.
- Format tests: write > read > inspect command stream, bounds, colours and sequence. Normalise expected format-specific differences, never demand impossible bitwise fidelity.
- Fuzz tests: malformed SVG, hostile archive entries, oversized raster images, corrupt machine files and extreme stitch counts.
- UI tests: autosave, long undo chain, crash recovery, missing asset, malformed project, keyboard-only path.
- Visual regression: stitch previews from fixed fixtures.
- Physical acceptance: empirical sew-outs with photos, machine/fabric/thread metadata and repeatability checks. Software-only validation cannot establish sewability.

## 10. Priority development backlog
| ID | Priority | Task | Completion test |
|----|----------|------|-----------------|
| E-001 | P0 | Repository scaffold, licences, CI, tests | all OS matrix jobs execute smoke tests |
| E-002 | P0 | Canonical mm geometry + document types | sample project round-trips |
| E-003 | P0 | Stitch events and deterministic pipeline | fixture parity |
| E-004 | P0 | Running stitch generator | straight and curved fixtures |
| E-005 | P0 | DST adapter | structurally valid DST in independent reader |
| E-006 | P0 | Canvas/hoop/viewports | smooth pan, zoom, accurate dimensions |
| E-007 | P0 | SVG import subset | transformed paths have correct mm dimensions |
| E-008 | P0 | Command history and autosave | recovery after simulated crash |
| E-009 | P0 | Satin generator + rail warnings | rails/rungs fixture set passes |
| E-010 | P0 | Polygon/holes and tatami | no hole cross-stitch regression |
| E-011 | P0 | Preview and playback | matches generated event stream |
| E-012 | P0 | PES adapter | validated export/import fixture set |
| E-013 | P0 | Machine profiles and preflight | reproducible warnings |
| E-014 | P1 | Thread management | colour order + exports consistent |
| E-015 | P1 | Production worksheets | counts, dimensions, colours checked |
| E-016 | P1 | Physical sew-out campaign | signed-off test report |
| E-017 | P2 | Assisted image vectorisation | editability and correction tests |
| E-018 | P2 | Batch conversion / CLI | deterministic multi-file output |

## 11. Known risks and mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Preview looks right, actual sewing fails | Very high | physical test gates, presets, clear model limitations |
| Unsupported PES/DST commands or vendor quirks | High | format fixtures, test machine profiles, no blanket support claim |
| Satin complexity grows uncontrollably | High | bounded two-rail first; staged algorithms and geometry diagnostics |
| Imported stitch files cannot recover design intent | High | separate stitch-only editing mode; explicit loss warnings |
| SVG scaling inconsistencies | High | mm unit tests; viewport/viewBox/transforms cases |
| Dependency licences conflict with distribution | High | pinned dependency audit before release; no GPL code copying |
| Slow redraw with large stitch counts | Medium | batched drawing and caches; profile before native acceleration |
| AI digitisation introduces weak designs | Medium | postpone; editable candidates and diagnostics rather than promises |
| Feature creep delays useful release | High | lock S1 to one-run-to-DST vertical slice |

## 12. Product decisions to settle later
- Final product name and repository name; working title only.
- Open-source versus commercial distribution, informed by actual dependency compliance.
- Supported OS order and minimum hardware specifications.
- Available embroidery machine(s), hoop sizes and fabrics for physical testing.
- Whether support for quilt patterns, sequins or free-standing lace merits independent modules.

## 13. Immediate next engineering move
Phase 1 prototype now implements the restricted SVG > running stitch > preview > DST > in-project decode round-trip. The next external gate is validating sample DST files in a separate embroidery viewer and on identified test machines. Satin and polygon-with-hole fill remain outstanding before S1 is complete. See `STATUS.md` for the implementation ledger.

## 14. Research references (checked 27 Oct 2026)
- Ink/Stitch (GPL-3.0): https://github.com/inkstitch/inkstitch
- Ink/Stitch satin design: https://inkstitch.org/docs/stitches/satin-column/
- pyembroidery (MIT, machine formats): https://github.com/EmbroidePy/pyembroidery
- libembroidery (zlib, alpha): https://github.com/Embroidermodder/libembroidery
- Qt for Python (LGPL/GPL/commercial): https://doc.qt.io/qtforpython-6/
