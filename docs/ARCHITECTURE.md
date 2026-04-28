> 🌏 [อ่านภาษาไทย](ARCHITECTURE.th.md)

# Thera AI Architecture

Thera is a local, retrieval-only CLI. Its main invariant is simple: canonical
text printed to stdout must come from the SQLite corpus row, not from a model,
summary, or normalization pass.

## Module Map

Current `src/thera/` modules:

| Module | Responsibility |
|---|---|
| `cli.py` | Typer application, command parsing, output rendering, exit-code mapping |
| `corpus.py` | Read-only SQLite access, search backend selection, MBU mapping helpers |
| `corpus_setup.py` | D-Tipitaka download/checksum/import and corpus validation |
| `citation.py` | Edition keys, citation rendering, Thai/Arabic numeral parsing |
| `sikkhapada.py` | Mahavibhanga/Bhikkhuni-vibhanga สิกขาบท parser and honest parse report |
| `__init__.py` | Package version surface |

There are no LLM calls in these modules. Retrieval commands open
`external/dtipitaka.db` through `corpus.open_db()`, which uses a read-only SQLite
URI with `mode=ro`.

## Command Surfaces

`cli.py` exposes:

- `thera read`
- `thera search`
- `thera compare`
- `thera cross-ref`
- `thera verify`
- `thera sikkhapada`
- `thera list volumes`
- `thera corpus info|init|validate`

The CLI uses explicit constants from spec §11:

- `EX_USAGE = 64`
- `EX_DATAERR = 65`
- `EX_SOFTWARE = 70`

Click/Typer default parser errors are remapped to 64 so test and real CLI
behavior stay aligned.

## Corpus Layout

The D-Tipitaka database has four source tables:

| Edition | Table | Volumes |
|---|---|---|
| Royal Thai | `thai_royal` | 45 |
| MCU Thai | `thai_mcu` | 45 |
| MBU Thai | `thai_mbu` | 91 |
| Pali Siam | `pali_siam` | 45 |

`corpus_setup.py` pins commit `645aa33` and validates the current expected row
total: `129_147`.

## Citation Invariants

Citation format comes from `citation.Citation.format()`:

```text
[ฉบับหลวง เล่ม 19 หน้า 257]
[มจร. เล่ม 19 หน้า 309]
[มมร. เล่ม 30 หน้า 412]
[พระบาลีสยามรัฐ เล่ม 19 หน้า 246]
```

Output citations use Arabic numerals. Input parsers accept both Arabic and Thai
digits through `parse_volume_arg()` and `parse_page_arg()`.

Forbidden patterns:

- No editionless citation.
- No mixed-edition citation for a single text block.
- No rewritten MBU volume in citations. If the DB row is MBU vol 88, the
  citation says `มมร. เล่ม 88`.

## Verbatim Contract

The high-risk rendering rule is: never let formatting libraries rewrite source
content. For full passage bodies, `cli.py` uses `sys.stdout.write()` through
helpers such as `_format_passage_text()` and `_print_passage_text()` so leading
tabs, source newlines, and source spacing survive.

Search snippets are the exception only in the narrow sense that snippets are
render-time excerpts. The source `content` field remains unchanged, and JSON
output includes the raw content plus match offsets.

Tests enforce byte-equal behavior by comparing subprocess CLI stdout with direct
SQL reads from `external/dtipitaka.db`.

## MBU Mapping Invariants

The MBU edition has 91 volumes and does not align 1:1 with Royal volumes.
`corpus.py` defines:

- `ROYAL_TO_MBU`
- `MBU_TO_ROYAL`
- `to_mbu_volumes(royal_volume)`
- `from_mbu_volume(mbu_volume)`

Invariant from spec §3 and LOKI R3:

- Every MBU volume 1..91 maps to exactly one Royal volume.
- No MBU volume appears in two Royal lists.
- `len(MBU_TO_ROYAL) == 91`.
- `len({m for ms in ROYAL_TO_MBU.values() for m in ms}) == 91`.

Command implications:

- `read --edition mbu` treats the volume argument as Royal and maps it.
- `read --edition mbu --raw-mbu-vol N` treats `N` as an exact MBU volume.
- `compare V:P:mbu` treats `V` as literal MBU volume.
- `cross-ref` folds MBU hits under Royal-equivalent groups.

## สิกขาบท Reading A

`sikkhapada.py` implements the v1.0 Reading A lock from DESIGN_LOG §26:

- bhikkhu: parse from Royal vols 1-2.
- bhikkhuni: parse from Royal vol 3 only.
- If parsed count is short, emit exit 70 diagnostic and abstain.

This is deliberate. The command must not fill missing bhikkhuni shared สิกขาบท
from inference. Reading B requires a future canonical mapping artifact.

## Test Conventions

Decision history lives in `DESIGN_LOG.md`; tests follow the locks there:

- §19.1: DEV does not write LOKI verdicts. Implementation handoff text uses the
  required "awaiting LOKI verify-and-sign" template.
- §19.2: every command flag needs CliRunner parser coverage with
  `runner.invoke(cli.app, [...], catch_exceptions=False)`.
- §19.3: commands crossing corpus or network boundaries need a real-corpus or
  real-network integration test using `subprocess.run`.

Additional conventions:

- Mock fixtures should include real-world bytes/data shapes where possible. The
  `verify` tests include the cp874 byte shape that previously broke strict
  TIS-620 decoding.
- Network tests are marked `@pytest.mark.verify` and skipped by default.
- Corpus init tests use pinned checksum payloads; real-corpus validate tests run
  against `external/dtipitaka.db`.

## Decision Sources

Use these files in order:

1. `DESIGN_LOG.md` for durable architecture decisions and LOKI verdicts.
2. `docs/CLI_SPEC.md` for the Phase 4 command contract.
3. `HANDOFF.md` for current task state.
4. `SESSION_LOG.md` for implementation evidence.

Spec amendments go through ARIA. Verification verdicts go through LOKI. DEV
implements and records evidence without claiming review outcomes.

## File-State Rules

`external/` is acquisition/corpus state, not public-repo source. Do not commit:

- `external/dtipitaka.db`
- `*.db`, `*.db-shm`, `*.db-wal`, `*.db-journal`
- `data/`
- `.aria/`, `.ai-memory/`, local handoff/session/design logs
- credentials or `.env` files

The public repository should contain source, tests, docs, packaging metadata,
and the MIT license. Users create the corpus locally with `thera corpus init`.
