# Changelog

## 0.10.0 — Contour controls and geometry checks

- Select, edit and remove individual contours inside compound fills, preserving undo/redo and schema-3 save/reopen.
- Edit retained Bézier anchors and handles on reference objects without flattening their curves. Coincident segment endpoints move together; intentional gaps are left alone.
- Add a design-diagnostics panel and `design-check` CLI command. Report risky source geometry and parameter choices without claiming that a design is machine-ready.
- Add headless geometry tests, desktop smoke tests and a CLI JSON diagnostic check. Stitch-generation algorithms are unchanged.

## 0.9.0 — Nodes and compound contours

- Editable vertices on flattened running/tatami shapes, with grid-snapped drag, midpoint insertion and vertex deletion.
- Open/close running contours from the Edit menu. Refuse invalid tatami topology before changing the document.
- Ctrl-select closed contours and combine them into a single even-odd tatami object; nested rings preserve holes, crossing/touching rings are rejected.
- Added undo/redo and project round-trip regression cases, plus Qt offscreen interaction tests.
- Still pre-alpha: no Bézier control-handle editor or machine-certified output.


## 0.8.0 — Precision workspace

- Added open-path drawing, a visible snap-grid control and absolute-anchor grid snapping.
- Improved narrow-stroke selection and deferred scene replacement after a drag ends.
- SVG paths now enter the desktop as separate running objects. A closed running path may be switched to tatami deliberately.
- Preserved original artwork, undo/redo and schema-3 project files. Added geometry and drawing tests.
- Still pre-alpha. Qt testing is in CI; supervised machine testing remains outstanding.


## v0.6.0 — 27 October 2026

- Introduced multi-object `DesignDocument` and object-specific styles, threads and visibility.
- Added schema-3 `.tbes` save/open with cubic reference geometry, source SHA-256,
  original style metadata and backward-compatible schema 1/2 reads.
- Added `compose`, `design-inspect`, `native-adapt`, and opt-in
  `design-promote-running` CLI commands.
- Implemented bounded inter-object jumps and explicit colour-change, TRIM and STOP
  event semantics. Unsupported DST trim/stop conversions fail closed.
- Updated SVG preview to reflect ordered thread colours and control markers.
- Retained running, satin, tatami and optional format adapter; added preservation
  of ordered thread palette to the optional adapter.
- Added synthetic multicolour sample and regression tests; four supplied native
  source examples passed external-archive preservation audit with 63 objects.
- Matched all 185 generated DST records with the distinct decoder in the user
  evidence archive. The real pyembroidery dependency and physical machines
  remain untested here.


## v0.5.0 — 27 October 2026

- Read-only `.ostch` parsing and geometry SVG output with two observed schema versions.
- Native project inspector, object-style census and corpus hash-audit script.
- Added synthetic regression tests; artwork from the vendor is not redistributed.
- Existing digitising/export engines remain unchanged. Native machine-stitch reconstruction not supported.


## 0.3.0, 27 October 2026

- Introduced explicit two-rail satin generation, with physical-width and crossing-rail checks.
- Added even-odd tatami scanline filling for closed contours, holes, concavities and rotated fill angles.
- Reduced redundant tatami needle-up travel by allowing guarded connections between successive rows; connectors are sewn only when the quantised segment stays in the fill area.
- Enforced the requested tatami maximum stitch length by rounding segment divisions upwards.
- Introduced project schema 2 for versioned stitch parameters; existing schema 1 projects retain a running-stitch fallback.
- Added satin and tatami CLI arguments and fixture previews.
- Corrected DST Y-axis orientation and the machine-axis header fields. Regenerate files exported with v0.2.0.
- Corrected DST `ST:` header accounting to include colour-stop records when present.
- Added fixed-byte DST axis tests, fill routing/hole checks and expanded regression coverage, including rotated-hole sew-path checks.
- Kept machine compatibility and sew-out verification open rather than claiming production readiness.

## 0.2.0, 27 October 2026

- Established the running-stitch conversion core with canonical millimetre geometry.
- Added a restricted SVG importer, group transforms, Bézier flattening and strict errors.
- Added DST export, internal structural read-back, hoop checks and stitch-order SVG preview.
- Added editable flattened-path `.tbes` project container (schema 1).
- Added CLI, fixtures and regression tests.

## 0.4.0 — Optional format bridge and source review (27 October 2026)

- Added separate `format_bridge` using pyembroidery's documented API, with no bundled third-party code.
- Added optional PES, PEC, EXP, JEF, VP3, XXX, U01 and TBF export paths through that dependency.
- Added opt-in `--independent-check` of native DST against pyembroidery's decoder; fails without the dependency and never pretends an internal read-back is independent.
- Kept G-code controller output disabled pending machine-specific safety review.
- Added reference and licence inventory for the research projects and a separate validation protocol.
- Added contract tests for adapter mapping, invalid colours, absent dependencies, fail-closed validation and unsupported formats.
- **Known limit:** The external package is unavailable in the local test environment; independent decoding and machine sew-outs remain unverified.

## 0.7.0 — Desktop foundation

- Added an optional Qt desktop editor with a measured hoop, object list and stitch preview.
- Objects can be moved, renamed, recoloured, hidden and reordered. Undo and redo are available.
- Existing `.tbes` projects open without a conversion step; older project versions are upgraded in memory and saved using the current editable format.
- Added atomic project saving, a preflight-gated DST export and bounded needle playback.
- Headless editing and save/reopen tests remain separate from the Qt smoke tests.
- Still pre-alpha: desktop rendering needs verification on each supported operating system, and no machine sew-out has been approved.
