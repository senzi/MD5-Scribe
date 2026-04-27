# MD5-Scribe

A human-AI collaborative system for learning and checking manual MD5 computation with printable worksheets and digital verification.

## Features

- Generates the 64 MD5 round steps for an input message.
- Provides a printable worksheet for each round.
- Keeps intermediate values hidden where the learner should compute them by hand.
- Verifies the five atom results for each round:
  - `T1 = A + f`
  - `T2 = T1 + M_j`
  - `T3 = T2 + K_i`
  - `ROT = RotateLeft(T3, s)`
  - `B_new = ROT + B`
- Adds a final worksheet and verification step for little-endian A/B/C/D byte ordering and digest concatenation.
- Includes the hex/binary reference appendix only on the first printable worksheet.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Then open:

```text
http://localhost:5000
```

## Test

```bash
python -m pytest
```

The core MD5 logic tests can also be run directly:

```bash
python tests/test_md5_logic.py
```

## Worksheet Notes

The printable worksheet is designed for hand calculation. The `f` result, `T1`, `T2`, `T3`, `ROT`, and `B_new` fields are left blank where the learner is expected to fill them in. Rotation bit grids are shown from bit 31 on the left to bit 0 on the right so that binary-to-hex grouping stays natural.

After all 64 rounds are complete, the final worksheet shows the final `A`, `B`, `C`, and `D` registers and leaves space to reverse each 32-bit word by byte before concatenating the final 128-bit MD5 digest.

Runtime task state and verification artifacts are written locally as `current_state.json`, `session_log.json`, and `final_report.md`; all are ignored by Git.
