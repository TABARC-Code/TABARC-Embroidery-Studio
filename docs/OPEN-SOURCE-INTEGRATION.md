# Open-source embroidery integration review

**27 October 2026 | TABARC Embroidery Studio v0.4.0 | research and integration notes**

This is a working-source review, not an assertion that all repos are mature, that a vendor supports every advertised machine, or that any generated file has been sewn. Links point to upstream projects. Do not commit an upstream project's source merely because it can be read publicly.

## Engineering decisions

1. **Use pyembroidery as an optional runtime file-format adapter.** It is MIT-licensed, implemented in Python and publishes a documented `EmbPattern` API. Our own geometry, stitch settings, preview and native DST engine remain independent. v0.4.0 adds an adapter for its supported PES, PEC, EXP, JEF, VP3, XXX, U01 and TBF outputs. Actual library execution remains to be validated in a dependency-enabled environment.
2. **Use pyembroidery as an optional second DST decoder.** `--independent-check` compares each needle event on the 0.1 mm grid before exporting a DST file. Inferred trims are disabled during the comparison. We must run this against the *real* package; the local tests use a contract fake, which is not proof of independent validation.
3. **Keep stitch generation independent.** Ink/Stitch, Embroidermodder and PEmbroider provide architectural research and test ideas, not source copied into the present prototype. We want controllable underlay, route optimisation and diagnostic reports without accidental GPL code mixing.
4. **Separate counted cross-stitch from machine digitising.** Embroiderly offers interesting charting/document concepts but XSD pattern files are not substitutes for PES/DST needle sequences.
5. **Keep direct machine control disabled.** OpenEmbroidery's G-code workflows are relevant for a future isolated hardware connector. A machine controller must require explicit machine-specific limits, homing and safety review. The CLI intentionally rejects `.gcode` export.
6. **Build a UI around the stitch-plan interface.** Compare Morale, Lilo, StitchFoundry and Embroidermodder for workflow ideas; don't bind the editor to any one external codebase. The GUI remains a separate milestone.

## Reference matrix

| Upstream | Link | Best research value | Language/stack | Licence note | Current decision |
| --- | --- | --- | --- | --- | --- |
| pyembroidery | https://github.com/EmbroidePy/pyembroidery | Machine file I/O, event semantics, independent decoding | Python | MIT | **Optional adapter coded** |
| libembroidery | https://github.com/Embroidermodder/libembroidery | C file parsers, independent fixture comparisons | C | zlib | Later test oracle/possible optional native backend |
| Embroidermodder 2 | https://github.com/Embroidermodder/Embroidermodder | Editor UX, estimates, import/export workflow | C/C++, Qt | Check current repo/individual components before reuse | Study; alpha software |
| Ink/Stitch | https://github.com/inkstitch/inkstitch | Underlay, routing, lettering and extension UI | Python/Inkscape | GPL; confirm component licences | Reference only |
| PEmbroider | https://github.com/CreativeInquiry/PEmbroider | Generative embroidery, fills, plotting | Java/Processing | GPLv3 and ACSL v1.4 wording; review before any reuse | Research only |
| Morale | https://github.com/vomitselfie/Morale | Standalone digitiser workflow, checks, lettering | Python/PySide6 | Earlier directory says GPL; verify licence at repo before reuse | Research only |
| Embroid-It | https://github.com/kfarr3/embroidit | Educational geometry and PES implementation | Java/JavaFX | BSD-3-Clause according to repository listing | Legacy reference |
| Embroiderly | https://github.com/embroidery-space/embroiderly | Counted cross-stitch design and document UX | Rust/TypeScript | GPL-3.0-or-later, docs CC-BY-SA-4.0 | Independent cross-stitch feature area |
| TurtleStitch | https://github.com/backface/turtlestitch | Beginner procedural pattern design | Browser/JavaScript | Verify per repo | UI concept reference |
| TurtleThread | https://github.com/TurtleThread/TurtleThread | Programmatic turtle strokes | Python | Verify per repo | Future scripting API idea |
| OpenEmbroidery | https://github.com/openembroidery | DIY machine controls, virtual machine, firmware | Mixed | Different repo licences | Isolated hardware research |
| OpenEmbroidery by F33RNI | https://github.com/F33RNI/OpenEmbroidery | DIY motion controller | Mixed | Verify per repo | Isolated hardware research |
| StitchFoundry | https://github.com/Stitchwright/StitchFoundry | Rust desktop architecture, UI and production feature checklist | Rust | MIT OR Apache-2.0 as stated upstream | Study; pre-release, no sew-outs claimed |
| Lilo | https://github.com/Kadwood/lilo | Offline desktop beginner experience, thread libraries, hoop selection | TypeScript | GPL-3.0 | Study UX and feature coverage, no source copied |
| myembro | https://github.com/linker2k/myembro | Mobile PES viewing concepts | Android | Verify per repo | Optional future mobile viewer |

**Licensing caution:** An MIT library dependency and a GPL application are very different propositions. The current TABARC project has not selected a distribution licence. A permissive dependency can usually be managed with correct notices; lifting GPL components into a differently licensed application needs a deliberate legal and project decision. No third-party source is included in v0.4.0.

## Important distinctions

- **Source available is not the same as permission to reuse.** Commercial programs may allow observation of public file-format behaviour, but reverse-engineering permissions vary by jurisdiction and contractual circumstances.
- **A source implementation is not a conformance test.** pyembroidery comparison is meaningful only when the real library is installed and tested against actual generated output.
- **File conversion is not digitisation.** An exporter does not improve density, underlay, pull compensation or fabric-specific stitch quality.
- **Passing software tests is not physical validation.** Keep a machine/model/hoop/needle/fabric/backing test log and supervised sew-out photographs.

## Next checks, in order

1. Install `pyembroidery` into a clean venv and run `python -m pytest -q` plus `tabarc-embroidery convert tests/fixtures/curve.svg curve.dst --independent-check`. Record installed version, hash and full comparisons.
2. Generate native DST + external PES/JEF/EXP/VP3; independently reopen using pyembroidery and a viewer. Record warnings and any inserted/modified events.
3. Add per-machine file profile, explicit physical hoop origin and usable area and selectable thread palettes, with source provenance for palette data.
4. Design object-level stitching and multi-colour ordering without tying the document to a single backend format.
5. Build a desktop UI proof-of-concept against the existing core, and leave the core runnable headlessly.

## Primary sources

- https://github.com/EmbroidePy/pyembroidery
- https://github.com/EmbroidePy/pyembroidery/blob/main/pyembroidery/DstReader.py
- https://github.com/Embroidermodder/libembroidery
- https://github.com/inkstitch/inkstitch
- https://github.com/CreativeInquiry/PEmbroider
- https://github.com/embroidery-space/embroiderly
- https://github.com/Stitchwright/StitchFoundry
- https://github.com/Kadwood/lilo
