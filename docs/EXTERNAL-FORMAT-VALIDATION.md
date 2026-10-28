# Optional pyembroidery checks

The v0.4.0 bridge is written against the *documented* pyembroidery API. Its tests use a lightweight contract fake. It **has not been executed against the real library** in this sandbox because package installation has no network access. Nothing here certifies hardware compatibility.

## Reproduce on a machine with pip access

```bash
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[test,formats]'
python -m pytest -q
python -m tabarc_embroidery formats
python -m tabarc_embroidery convert tests/fixtures/curve.svg /tmp/curve.dst --independent-check
python -m tabarc_embroidery convert tests/fixtures/curve.svg /tmp/curve.pes --thread-hex '#102030'
```

Change `/tmp/curve...` to a writable folder under Windows; Windows PowerShell needs quotes around the six-digit colour argument. These are *test artefacts*, not machine-verified patterns.

## Comparison protocol

- Validate DST with the independent decoder, compare `STITCH`, `JUMP`, `COLOUR_CHANGE`, `END` events on the 0.1 mm grid. Inferred trim post-processing is disabled for fidelity.
- Record a pyembroidery version, Python version, platform, each file SHA-256 and decoded stitch counts/bounds, including the saved preview orientation.
- Reopen every converted PES/JEF/EXP/VP3 file in an independent viewer. Some export formats normalise the sequence or insert events. A format writer returning successfully is not a guarantee of equivalent output.
- Only then carry out supervised sew-outs on scrap fabric, logging machine model, firmware, hoop, thread, needle, stabiliser and any faults.

**Limitation:** v0.4.0 only has one placeholder thread colour and does not generate underlay, reliable trims, tie-offs or multiple thread-change sections. Some machine formats may therefore produce less useful files than the extension suggests.
