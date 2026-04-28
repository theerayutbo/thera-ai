> 🌏 [อ่านภาษาไทย](QUICKSTART.th.md)

# Thera AI Quickstart

This guide gets from a fresh checkout to useful Tipitaka lookup in about five
minutes. Thera is offline-first once the D-Tipitaka SQLite corpus exists at
`external/dtipitaka.db`.

## Prerequisites

- Python 3.11 or newer.
- About 600 MB of disk space for `external/dtipitaka.db`.
- Network access for the initial `corpus init` download and for `verify`.
- No network is needed for `read`, `search`, `compare`, `cross-ref`, or
  `sikkhapada` after the corpus exists.

Install from a local clone:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
thera --help
```

Developer shortcut without installation:

```bash
PYTHONPATH=src python -m thera.cli --help
```

## Corpus Setup

Download and checksum-verify the pinned D-Tipitaka corpus:

```bash
thera corpus init
```

If `external/dtipitaka.db` already exists, Thera refuses to overwrite it:

```text
corpus init failed: corpus already exists at external/dtipitaka.db; pass --force to overwrite
```

Validate the installed database:

```bash
thera corpus validate
```

Expected v1.0 corpus shape:

```text
pali_siam: 21915 rows, 0 NULL content
thai_mbu: 62380 rows, 0 NULL content
thai_mcu: 25155 rows, 0 NULL content
thai_royal: 19697 rows, 0 NULL content
total: 129147 rows (expected 129147, ±1% tolerance)
validate OK
```

## Session 1: Read One Royal Page

```bash
thera read 1 1
```

The output starts:

```text
[ฉบับหลวง เล่ม 1 หน้า 1]
1

                    พระวินัยปิฎก
                        เล่ม ๑
                มหาวิภังค์ ปฐมภาค
```

That citation and body are emitted from:

```sql
SELECT items, content FROM thai_royal WHERE volume = 1 AND page = 1;
```

Thai numeral input works:

```bash
thera read ๔๓ ๑
```

## Session 2: Search for a Topic

```bash
thera search "อริยสัจ" --limit 2
```

On systems without SQLite ICU FTS loaded, search falls back to a linear scan:

```text
[fallback: linear scan, slow]
[ฉบับหลวง เล่ม 4 หน้า 16]
items: 14
...
[truncated at 2 — use --limit to expand]
```

Use `--edition all` to search all four editions:

```bash
thera search "อริยสัจ" --edition all --limit 1
```

## Session 3: Compare Two Editions

Compare Royal vol 43 page 1 with the aligned MBU volume:

```bash
thera compare 43:1 88:1:mbu
```

The command reports the shared Royal cluster and keeps both citations separate:

```text
royal_alignment_note: 43
--- A ---
[ฉบับหลวง เล่ม 43 หน้า 1]
...
--- B ---
[มมร. เล่ม 88 หน้า 1]
...
```

The common mistake is to type MBU vol 43 for Royal vol 43:

```bash
thera compare 43:1 43:1:mbu
```

Thera exits 65 with:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

## Session 4: Cross-Reference a Topic

```bash
thera cross-ref "อริยสัจ" --limit 1
```

Current real-corpus output starts:

```text
[fallback: linear scan, slow]
เล่ม 1
  Royal: 0 hits
  มมร. (vol 1+3): 4 hits combined  (vol 1 pages 186, 205, 211; vol 3 pages 478)
```

The important detail is the grouping: MBU volumes are folded under their
Royal-equivalent volume. MBU never becomes the top-level grouping key.

## Session 5: สิกขาบท Lookup

Fetch a specific bhikkhu สิกขาบท:

```bash
thera sikkhapada bhikkhu --rule 1
```

The output starts:

```text
[ฉบับหลวง เล่ม 1 หน้า 14]
10

                ปาราชิกกัณฑ์ ปฐมปาราชิกสิกขาบท
                        เรื่องพระสุทินน์
```

List mode is strict. If the parser cannot find every expected สิกขาบท, it exits
70 instead of inventing missing entries:

```bash
thera sikkhapada bhikkhuni
```

Current v1.0 Reading A diagnostic:

```text
sikkhapada parser yielded 139 bhikkhuni rules, expected 311.
delta: 172 rule(s); abstaining per §1.4 — never pad or truncate.
```

## Session 6: Verify Against 84000.org

When the network is available:

```bash
thera verify 1 1
```

This compares the Royal passage against 84000.org using cp874/TIS-620 decode.
If DNS or outbound network is blocked, the command exits 70:

```text
network failure while fetching https://84000.org/tipitaka/read/r.php?B=1&A=1: ...
```

Offline corpus commands remain usable in that state.

## Common Workflows

Cross-edition reading:

```bash
thera read 43 1
thera read 43 1 --edition mcu
thera read 43 1 --edition mbu
```

Royal vol 43 maps cleanly to MBU vol 88, so the MBU command returns page 1
directly. Royal vol 25 maps to nine MBU volumes, so Thera asks for a raw MBU
volume:

```bash
thera read 25 1 --edition mbu
thera read 25 1 --edition mbu --raw-mbu-vol 39
```

Citation copy-paste:

```bash
thera read ๔๓ ๑
thera compare ๔๓:๑ ๘๘:๑:mbu
```

## Troubleshooting

### FTS Missing

Symptom:

```text
[fallback: linear scan, slow]
```

This is not a failure. SQLite ICU FTS is unavailable, so Thera uses `LIKE`
against the local corpus. Results are still verbatim; the scan is just slower.

### Network Blocked

Symptom:

```text
network failure while fetching https://84000.org/...
```

Only `thera verify` needs the network. Use offline commands while disconnected:

```bash
thera read 1 1
thera search "อริยสัจ"
thera compare 43:1 88:1:mbu
```

### MBU Mismatch

Symptom:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

MBU has 91 volumes; Royal/MCU/Pali have 45. Use the suggested MBU volume, or
use `thera read <royal-vol> <page> --edition mbu` and follow any
disambiguation prompt.
