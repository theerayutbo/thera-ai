> 🌏 [อ่านภาษาไทย](README.th.md)

# Thera AI

Zero-hallucination Tipitaka retrieval CLI: verbatim canonical text, citations,
and cross-edition checks with no synthesis.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: v1.0 candidate](https://img.shields.io/badge/status-v1.0_candidate-blue.svg)](DESIGN_LOG.md)
[![PyPI: later](https://img.shields.io/badge/PyPI-later-lightgrey.svg)](#quick-install)

## What Is This

Thera AI is a command-line reader for the Thai Tipitaka corpus. It retrieves
canonical text directly from a local D-Tipitaka SQLite database and prints the
source passage with an edition, volume, and page citation.

The philosophy is Buddhawajana-first: the tool retrieves and compares the text;
the reader interprets. Retrieval mode makes zero LLM calls, writes no summaries,
and does not smooth over source typos or formatting. If the corpus does not give
enough information, the command exits with a diagnostic instead of guessing.

This is not a chatbot, not an Atthakatha/commentary layer, and not a
สิกขาบท-fabrication engine. It can surface differences between Royal, MCU, MBU,
and Pali Siam editions, but it does not adjudicate those differences for the
user.

## Quick Install

Published package installation is planned after v1.0 public release. From a
local clone today:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Then check the binary:

```bash
thera --help
```

v1.1 ships the pinned D-Tipitaka source dumps in `vendor/D-tipitaka/1.2/`.
After cloning the full repo, `thera corpus init` can build
`external/dtipitaka.db` from local vendored files without contacting GitHub.

For development without installing, use:

```bash
PYTHONPATH=src python -m thera.cli --help
```

## 5-Minute Walkthrough

Initialize the corpus if `external/dtipitaka.db` is not present:

```bash
thera corpus init
```

Validate the local database:

```bash
thera corpus validate
```

Expected current corpus summary:

```text
pali_siam: 21915 rows, 0 NULL content
thai_mbu: 62380 rows, 0 NULL content
thai_mcu: 25155 rows, 0 NULL content
thai_royal: 19697 rows, 0 NULL content
total: 129147 rows (expected 129147, ±1% tolerance)
validate OK
```

Read Royal vol 1 page 1:

```bash
thera read 1 1
```

The output starts with the citation and verbatim source row:

```text
[ฉบับหลวง เล่ม 1 หน้า 1]
1

                    พระวินัยปิฎก
                        เล่ม ๑
                มหาวิภังค์ ปฐมภาค
```

Search the Royal edition:

```bash
thera search "อริยสัจ" --limit 2
```

If SQLite ICU FTS is not loaded, Thera still works and announces the fallback:

```text
[fallback: linear scan, slow]
[ฉบับหลวง เล่ม 4 หน้า 16]
items: 14
...
[truncated at 2 — use --limit to expand]
```

Compare Royal ปัฏฐาน with the aligned MBU volume:

```bash
thera compare 43:1 88:1:mbu
```

The output includes:

```text
royal_alignment_note: 43
--- A ---
[ฉบับหลวง เล่ม 43 หน้า 1]
...
--- B ---
[มมร. เล่ม 88 หน้า 1]
...
```

Verify against 84000.org when network is available:

```bash
thera verify 1 1
```

If the network is blocked, `verify` exits 70 and offline commands such as
`read`, `search`, `compare`, `cross-ref`, and `sikkhapada` continue to work.

## Architecture Overview

Thera uses the D-Tipitaka SQLite corpus at commit `645aa33`. The local database
is about 555 MB on disk and contains 129,147 rows across four source tables:

| Edition key | Table | Role | Volumes |
|---|---|---|---|
| `royal` | `thai_royal` | Primary Thai Royal edition | 45 |
| `mcu` | `thai_mcu` | MCU Thai edition | 45 |
| `mbu` | `thai_mbu` | MBU Thai edition | 91 |
| `pali` | `pali_siam` | Pali Siam in Thai script | 45 |

The Royal edition is the default reading surface. MCU, MBU, and Pali Siam are
available for cross-reference and comparison. The MBU edition uses 91 volumes,
so Thera ships a Royal-to-MBU mapping layer and a mismatch detector for the
most common user error: assuming Royal volume 43 and MBU volume 43 align.

## Citation Format

Every canonical text block has an edition-disclosing citation:

```text
[ฉบับหลวง เล่ม 19 หน้า 257]
[พระบาลีสยามรัฐ เล่ม 19 หน้า 246]
[มจร. เล่ม 19 หน้า 309]
[มมร. เล่ม 30 หน้า 412]
```

Edition keys:

| Key | Display |
|---|---|
| `royal` | `ฉบับหลวง` |
| `mcu` | `มจร.` |
| `mbu` | `มมร.` |
| `pali` | `พระบาลีสยามรัฐ` |

Input accepts Arabic or Thai numerals, for example `thera read ๔๓ ๑`.
Output citations use Arabic numerals for stable copy/paste.

## Edition Philosophy

Thera keeps editions side by side. It does not collapse them into a single
harmonized text. When editions differ, the CLI surfaces the difference with
separate citations and leaves interpretation to the reader.

MBU volume numbering is intentionally explicit. `thera compare 43:1 43:1:mbu`
exits with:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

That error is a feature: it prevents silent citation drift.

## Limitations

v1.0 is literal and intentionally conservative.

- `thera sikkhapada bhikkhuni` uses Reading A from DESIGN_LOG §26: Royal vol 3
  only. The corpus contains 139 fully stated bhikkhuni สิกขาบท there, not 311,
  so the command exits 70 with a transparent 139/311 diagnostic instead of
  filling gaps from inference.
- `thera sikkhapada bhikkhu` currently parses 224/227 สิกขาบท and exits 70 in
  list mode rather than padding the missing slots.
- Atthakatha/commentary, NotebookLM curated slices, and canonical personas are
  out of scope for v1.0.
- `verify` requires network access to 84000.org. Offline retrieval still works.
- v1.1 vendored corpus sources reduce the kit119 upstream single point of
  failure for corpus initialization, but they do not change the canonical
  snapshot: all data remains pinned to commit `645aa33`.
- There is no long-lived cache or service process; each CLI invocation opens the
  SQLite database directly.

## Contributing

The decision history is in `DESIGN_LOG.md`. The project uses an ARIA-LOKI-DEV
cycle: ARIA writes product/spec decisions, DEV implements, and LOKI verifies
before the next step. New behavior should preserve the verbatim contract, add
CliRunner parser tests, and include real-corpus integration where a command
touches the corpus or network.

## Acknowledgments

- Thera AI ships with a vendored copy of the
  [kit119/D-tipitaka](https://github.com/kit119/D-tipitaka) database
  (commit `645aa33`, 2011), dedicated to open-source / public-domain-leaning
  redistribution per its `README.TXT`. See [NOTICE](NOTICE) for the full
  attribution chain.
- `84000.org` for the live Royal/MCU comparator used by `thera verify`.
- SQLite, ICU, Typer, Rich, pytest, Ruff, and the Python packaging ecosystem.

## License

Thera AI is released under the MIT License. See [LICENSE](LICENSE).
