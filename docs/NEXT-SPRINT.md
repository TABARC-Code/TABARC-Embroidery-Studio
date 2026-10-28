# v0.7.0 priorities

1. **Standalone PySide6 read-only visual inspector**: open schema-3 `.tbes`, display object list, stitch settings, thread palette and preview with accessible controls. Keep no external dependency for CLI engine.
2. **Object manipulation**: reorder, hide, recolour, rename, change stitch settings, undo/redo, with schema-3 autosave and migration tests. Never implicitly digitise imported reference objects.
3. **Validate against a pinned real pyembroidery dependency**: independent DST decoding and sample PES/JEF files; add colour segment and explicit TRIM command tests. Any unsupported operator STOP must remain blocked.
4. **Machine production safeguards**: planned underlay, tie-in/tie-off, density analysis and pull compensation. Establish machine profile and origin semantics before enabling hardware workflows.
5. **Additional native import research**: benchmark a selected vendor Running source against paired reference machine files; keep reference, approximation and exact-regeneration claims separate.
6. **Supervised sew-out protocol**: test scraps, material/hoop registration, thread charts, and explicit acknowledgement that no machine files are certified.
