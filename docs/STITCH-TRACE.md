# Needle event trace — v0.11.0

The `DesignTrace` object carries the regular `StitchPlan` plus a parallel tuple of source object IDs. It does **not** change the `.tbes` schema, DST export or machine events. All mapping is regenerated from the current document, which keeps saved files smaller and prevents stale indices surviving a geometry edit.

## Ownership rules

- Sewed steps belong to the object being digitised.
- Needle-up travel into an object belongs to the *arriving* object, not the one last sewn.
- An automatically inserted thread change belongs to the arriving object. Explicit STOP/TRIM/COLOUR_CHANGE commands are attributed to their own control objects.
- Hidden objects and non-sewing references contribute no events.
- The final END event has no owner.

Event numbers are zero-based internally and in the CLI. The desktop displays human-friendly event numbers, one higher than the stored index.

## Inspect the sequence

```sh
tabarc-embroidery design-trace examples/multi-object.tbes --limit 20
tabarc-embroidery design-trace examples/multi-object.tbes --object-id red-line --start 10 --limit 20
```

The command returns up to 1,000 rows per request, but retains original indices even when filtering. The separate `findings` array is capped at 100 and reports only the first instance of each problem type for each object. Reported coordinates are the generated, quantised **needle destinations** in millimetres.

## Diagnostics and limitations

A destination outside the selected hoop is an error. Consecutive needle-down steps shorter than 0.3 mm or longer than 8 mm produce warnings; jumps are never treated as stitches. These checks are deliberately limited. Multiple legitimate sewing strategies use tiny stitches, and a valid preview can still bunch, distort or snag fabric.

The desktop diagnostics dock selects the affected object and seeks to the recorded event; editing the document discards the old sequence. Physical machine sew-outs are still essential, and no thread or fabric suitability is inferred.
