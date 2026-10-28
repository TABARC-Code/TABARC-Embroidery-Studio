# Status

**v0.7.0, 27 October 2026 — multi-object document model and schema-3 projects implemented; pre-alpha.**

106 automated tests passed, one optional-dependency module skipped because
pyembroidery could not be installed here. A separate decoder supplied in the
reconstruction evidence pack matched all 185 records in the generated multi-
object DST example. Four original native `.ostch` files (63 objects) passed
reference-only schema-3 save/open checks; vendor designs are excluded from
this release archive.

The new `compose` CLI supports individually configured running, satin, tatami,
reference and control objects. Source cubic reference geometry and metadata
are retained, with opt-in native Running approximation. STOP and TRIM remain
explicit events and unsupported machine exports fail closed.

No GUI, physical sew-outs or completed machine-profile validation.
See [object model](OBJECT-DOCUMENT.md) and [next sprint](NEXT-SPRINT.md).

Desktop workbench available as an optional PySide6 installation. Local Qt execution was unavailable during development; an offscreen CI smoke test has been added. Physical machine testing is still outstanding.
