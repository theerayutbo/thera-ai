# Thera CLI Specification — Phase 4

**Authored**: 2026-04-26 by ARIA (Opus, plan/spec tier)
**Status**: draft awaiting LOKI gate review (per HANDOFF / DESIGN_LOG §14)
**Target implementer**: DEV (Codex)
**Lock contracts**: DESIGN_LOG §1-§14 — verbatim-only, multi-edition, SQLite-direct primary, MIT, Python+typer.

---

## §0 Purpose & Reading Order

This spec converts Phase 3 capabilities (canon ingested + KM reference map) into Phase 4 deliverables (a usable CLI that retrieves verbatim canon with correct cross-edition handling). It is **the contract** between ARIA (designer) and DEV (implementer), with LOKI as the gate.

Read in order: §1 guarantees → §2 citation lock → §3 MBU mapping (most error-prone path) → §4-§10 per-command specs → §11 error model → §12 test contract → §13 implementation sequence.

LOKI: when reviewing, focus first on §2 (citation format), §3 (MBU mapping), and §6 (compare) — these are where Phase 3 findings will be silently broken by naïve implementations.

---

## §1 Product Guarantees (non-negotiable)

These are the user-facing promises every command must keep. Any DEV change that breaks one of these is automatically a LOKI block.

1. **Verbatim contract**: every byte of canonical text printed to stdout came verbatim from the SQLite corpus row. No normalization. No whitespace stripping inside the body. No silent typo correction (LOKI's vol-37 spot-check confirmed `ขอนอบน้อมแต่` typo is preserved — that's the bar).
2. **Citation discipline**: every canonical text block carries a citation that names volume, page, and edition. No edition disclosure = silent error class.
3. **Edition honesty**: when a command crosses editions (search/compare/cross-ref), output must show which edition each result came from. Never mix editions under a single citation.
4. **No synthesis**: zero LLM calls. Zero paraphrase. Zero "summary." If a command cannot honor a request literally, it exits with code 64 (`EX_USAGE`) and a clear message — it does not approximate.
5. **Read-only corpus**: all DB connections open with `mode=ro` URI. Already enforced in `corpus.py:open_db`. DEV must not regress.
6. **Determinism**: same input → same output, byte for byte. Implies: stable result ordering in `search` / `cross-ref`, stable rendering in `read` / `compare`. No timestamps in output. No locale-sensitive sorting.

---

## §2 Citation Format (LOCKED)

`citation.py` already implements canonical Thai format. Phase 4 locks this and adds machine-readable variants.

### §2.1 Default (human, Thai)

```
[ฉบับหลวง เล่ม 19 หน้า 257]
[พระบาลีสยามรัฐ เล่ม 19 หน้า 246]
[มจร. เล่ม 19 หน้า 309]
[มมร. เล่ม 30 หน้า 412]
```

Format string: `[{EDITION_DISPLAY[ed]} เล่ม {volume} หน้า {page}]` — already in `Citation.format()`. Volume and page are Arabic numerals (NOT Thai numerals) — this matches D-Tipitaka's source rendering and avoids ambiguity in CLI scrollback.

### §2.2 Machine-readable (JSON output mode)

When invoked with `--format=json`, every command emits one JSON object per result with this shape:

```json
{
  "citation": {
    "edition": "royal",
    "edition_display": "ฉบับหลวง",
    "volume": 19,
    "page": 257,
    "pitaka": "sutta"
  },
  "items": "[๑๖๔๔]",
  "content": "<verbatim — no escape beyond JSON minimum>"
}
```

### §2.3 Cross-edition citations (MBU split case)

When `compare` or `cross-ref` returns a Royal volume that maps to multiple MBU volumes (per §3), citations stay per-edition — never combined under a single shared volume number. Example output for Royal vol 25 ↔ MBU split:

```
[ฉบับหลวง เล่ม 25 หน้า 1]
[มมร. เล่ม 39 หน้า 1] [มมร. เล่ม 40 หน้า 1] ... [มมร. เล่ม 47 หน้า 1]   (9 MBU vols cover this Royal vol)
```

### §2.4 Forbidden citation patterns (LOKI gate items)

- ❌ `[เล่ม 43 หน้า 1]` (no edition)
- ❌ `[ฉบับหลวง/มมร. เล่ม 43 หน้า 1]` (mixing editions under one volume)
- ❌ Thai numerals in **citation OUTPUT** (`เล่ม ๔๓` is for the canonical text body, not the citation overlay)
- ❌ Auto-translated MBU vol number to Royal vol number in citation (e.g., showing `มมร. เล่ม 25` when DB row was `volume=88`) — citation must reflect the actual DB row that produced the text.

### §2.5 Input-side numeral parsing (per LOKI §16 OQ #1)

CLI **input** accepts both Arabic and Thai numerals for volume/page args. KM citations use Thai numerals, so users copy-pasting `[ฉบับหลวง เล่ม ๔๓ หน้า ๑]` into `thera read ๔๓ ๑` must work. Implementation: `citation.parse_volume_arg(s) -> int` and `citation.parse_page_arg(s) -> int` normalize Thai → Arabic before query. Apply at every CLI int-arg site (`read`/`compare`/`verify` args). Output side remains Arabic-only per §2.1.

---

## §3 MBU Mapping Layer (LOKI flag — handle as default, not edge case)

Per LOKI's 2026-04-26 reverse-index finding: **`thai_mbu` has 91 volumes, not 45**. Royal/Pali/MCU = 1:1 (45 vols each). MBU = many-to-one against Royal for 36/45 (80%) of Royal vols. Naïve `WHERE volume=N` against `thai_mbu` returns silently-wrong content.

### §3.1 Drop-in mapping module (DEV: integrate verbatim from `docs/corpus-mbu-volume-mapping.md`)

Add to `src/thera/corpus.py`:

```python
# --- Royal ↔ MBU volume mapping (LOKI 2026-04-26, docs/corpus-mbu-volume-mapping.md) ---
# Royal/Pali/MCU = 1:1 (45 vols); MBU uses 91-vol finer split.
# DEV: do NOT modify this dict by hand — re-derive via SQL query in mapping doc.

ROYAL_TO_MBU: dict[int, list[int]] = {
    1: [1, 2, 3], 2: [4], 3: [5], 4: [6], 5: [7], 6: [8], 7: [9], 8: [10],
    9: [11, 12], 10: [13, 14], 11: [15, 16],
    12: [17, 18], 13: [19, 20, 21], 14: [22, 23],
    15: [24, 25], 16: [26], 17: [27], 18: [28, 29], 19: [30, 31],
    20: [32, 33, 34], 21: [35], 22: [36], 23: [37], 24: [38],
    25: list(range(39, 48)), 26: list(range(48, 55)), 27: list(range(55, 63)), 28: [63, 64],
    29: [65, 66], 30: [67], 31: [68, 69], 32: [70, 71, 72], 33: [73, 74],
    34: [75, 76], 35: [77, 78], 36: [79], 37: [80, 81], 38: [82, 83], 39: [84],
    40: [85], 41: [86], 42: [87], 43: [88], 44: [89, 90], 45: [91],
}

MBU_TO_ROYAL: dict[int, int] = {
    mbu: royal for royal, mbus in ROYAL_TO_MBU.items() for mbu in mbus
}


def to_mbu_volumes(royal_volume: int) -> list[int]:
    """Translate a Royal volume number into the list of MBU volume(s) that cover it."""
    if royal_volume not in ROYAL_TO_MBU:
        raise ValueError(f"Royal volume {royal_volume} not in 1..45")
    return ROYAL_TO_MBU[royal_volume]


def from_mbu_volume(mbu_volume: int) -> int:
    """Translate a MBU volume number into the Royal volume it falls under."""
    if mbu_volume not in MBU_TO_ROYAL:
        raise ValueError(f"MBU volume {mbu_volume} not in 1..91")
    return MBU_TO_ROYAL[mbu_volume]
```

### §3.2 When mapping must be consulted

| Code path | Consult mapping? |
|---|---|
| `read --edition royal\|mcu\|pali` (volume arg) | No — direct |
| `read --edition mbu` (Royal volume arg) | **Yes** — translate to MBU vol(s); see §4.2 |
| `read --edition mbu --raw-mbu-vol N` (escape hatch) | No — direct (advanced flag, see §4.4) |
| `compare <royal_ref> <mbu_ref>` | **Yes** — verify MBU vol falls in correct Royal cluster |
| `search` per-edition results | Reporting only — citation uses MBU's own vol number; no remapping |
| `cross-ref` aggregation | **Yes** — group MBU hits by their Royal-equivalent vol |
| `verify` (84000 ground-truth diff) | Edition-specific; if MBU vol arg given, apply mapping before lookup |

### §3.3 Page-level alignment caveat (LOKI flag #3)

Within a Royal vol that maps to multiple MBU vols (e.g., Royal 25 → MBU 39-47), page numbers do NOT continue arithmetically across the MBU split. Royal vol 25 page 200 ≠ any single (mbu_vol, page) by formula. **Page-level cross-edition mapping requires content lookup, not arithmetic.**

Implementation rule for `compare` page-anchored cases:
1. Read Royal `(vol, page)` content.
2. Take the first ~80 chars (after stripping Items column markers).
3. FTS-search MBU for that snippet; first hit is the page-equivalent.
4. If 0 hits or >3 hits, return `[INSUFFICIENT MAPPING — manual lookup]` with both candidate ranges.

Cache decisions: keep this lookup stateless for v1; cache layer is a v2 concern.

---

## §4 Command: `thera read` (priority 2 — implement after `search`)

### §4.1 Synopsis

```
thera read <volume> <page> [--edition royal|mcu|mbu|pali] [--format text|json]
```

### §4.2 Behavior

| Edition | Volume arg interpretation | Lookup |
|---|---|---|
| royal (default) | Royal vol 1-45 | `WHERE volume=N` on `thai_royal` |
| mcu | Royal vol 1-45 (1:1) | `WHERE volume=N` on `thai_mcu` |
| pali | Royal vol 1-45 (1:1) | `WHERE volume=N` on `pali_siam` |
| mbu | **Royal** vol 1-45 → mapped via §3 | If 1 MBU vol: direct lookup at that page; if >1 MBU vols: see §4.3 |

### §4.3 MBU multi-volume case (NEW — LOKI flag #1)

When `--edition mbu` is used and the Royal volume maps to multiple MBU volumes:

- If `page` falls within a single MBU vol's range: return that passage directly.
- If user does not know which MBU sub-volume their page is in: print all MBU vols that cover this Royal vol with their page ranges, then exit code 65 (`EX_DATAERR`):

```
Royal vol 25 spans 9 MBU vols. Specify which MBU vol holds page 200:
  [มมร. เล่ม 39] pages 1-578
  [มมร. เล่ม 40] pages 1-624
  ...
Use `thera read 25 200 --edition mbu --raw-mbu-vol 41` to disambiguate.
```

### §4.4 Escape hatch flag

`--raw-mbu-vol N` — bypass mapping, query MBU directly with the MBU vol number. For advanced users who already know the MBU coordinate. Documented; not promoted in `--help` summary.

### §4.5 Acceptance criteria

- [ ] `thera read 1 1` returns Royal vol 1 page 1 (Mahavibhanga opening) byte-for-byte equal to `SELECT content FROM thai_royal WHERE volume=1 AND page=1`.
- [ ] `thera read 43 1 --edition mcu` returns Patthana Part 4 Royal-aligned content.
- [ ] `thera read 43 1 --edition mbu` returns the disambiguation message (vol 43 → MBU vol 88; if page valid in mbu vol 88, returns content directly).
- [ ] `thera read 25 1 --edition mbu` triggers the multi-vol disambiguation path.
- [ ] `thera read 25 1 --edition mbu --raw-mbu-vol 39` returns MBU vol 39 page 1 directly.
- [ ] `thera read 99 1` exits 64 with "volume 99 out of range 1..45".
- [ ] `thera read 1 9999` exits 1 with "no passage at (1, 9999, royal)".
- [ ] All output respects §1 verbatim contract — no stripping inside content body.

---

## §5 Command: `thera search` (priority 1 — IMPLEMENT FIRST)

### §5.1 Synopsis

```
thera search <query> [--edition royal|mcu|mbu|pali|all] [--limit N] [--format text|json]
```

### §5.2 Behavior

- Default edition: `royal`. `--edition all` runs the same query against all four editions and prints results grouped by edition.
- Result is a list of (volume, page, items, snippet) tuples. Snippet = ±80 chars around the match, with the matched span marked (rich `[bold]` for text mode; raw position offsets for json mode). **Snippet match-marking is rendering only; underlying canonical text remains byte-exact per §1.1** — DEV must not mutate the source content to inject markers, only annotate render-time. (LOKI §16 R1.)
- Ordering: by volume ASC, then page ASC. Stable.
- `--limit` caps per-edition. Default 20.

### §5.3 FTS implementation guidance

D-Tipitaka ships two FTS virtual tables: `fts4` (porter) and `fts4-icu` (Thai ICU tokenizer). DEV must:
1. Detect which is loaded at DB-attach time (try `SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts4%'`).
2. Prefer `fts4-icu` for queries containing Thai characters (regex `[฀-๿]`).
3. Fall back to `LIKE '%query%'` linear scan if neither FTS table is loaded — explicitly warn user that this is slow.

The ICU extension is `libsqliteicu.{so,dylib}`. DEV: implement detection + load via `conn.enable_load_extension(True); conn.load_extension(path)`. If extension not found at runtime, fall back path #3 above; do not fail the command outright.

### §5.4 Acceptance criteria

- [ ] `thera search "อนิจจัง"` returns ≥1 hit with citation `[ฉบับหลวง เล่ม X หน้า Y]` and a snippet containing the search term.
- [ ] `thera search "ปฏิจจสมุปบาท" --edition all` returns hits grouped by edition; no edition cross-contamination in citations.
- [ ] `thera search "" ` exits 64 (empty query rejected).
- [ ] `--format json` produces well-formed JSON-lines (one object per result line).
- [ ] If FTS extension cannot be loaded, command still runs (LIKE fallback) with explicit `[fallback: linear scan, slow]` warning to stderr.
- [ ] Result count obeys `--limit`; results past the limit are not silently truncated — a final `[truncated at N — use --limit to expand]` note is printed.
- [ ] No paraphrase, no summary, no AI commentary in output.

---

## §6 Command: `thera compare`

### §6.1 Synopsis

```
thera compare <ref_a> <ref_b> [--format text|json]
```

`<ref>` shape: `V:P` (defaults to royal) or `V:P:edition` (e.g., `19:257:mcu`, `30:412:mbu`).

### §6.2 Behavior

- Each ref is resolved to a Passage independently using the same path as `thera read`.
- For MBU refs, the V in `V:P:mbu` is interpreted as the **MBU's own** volume number (1..91), not Royal-equivalent. Rationale: users typing a `compare` already have an exact citation in hand. ARIA decision: keep `compare` literal, push translation to `read`.
- Output: side-by-side panels (rich) or two JSON objects with shared `comparison_id` field.
- If both refs land in the same Royal cluster (per MBU_TO_ROYAL), include a `royal_alignment_note` field showing the shared Royal vol — useful context, not a guarantee of textual equivalence.

### §6.3 Acceptance criteria

- [ ] `thera compare 43:1 43:1:mcu` shows Royal Patthana opening alongside MCU paraphrase (both verbatim, both with own citation).
- [ ] `thera compare 43:1 88:1:mbu` shows Royal Patthana opening alongside MBU vol 88 page 1, with `royal_alignment_note: 43`.
- [ ] `thera compare 43:1 43:1:mbu` exits 65 with "MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?" (use ROYAL_TO_MBU and MBU's own page-1 header to detect the divergence).
- [ ] Both panels render content respecting verbatim contract (no edge whitespace stripping).

---

## §7 Command: `thera cross-ref`

### §7.1 Synopsis

```
thera cross-ref <keyword> [--limit N] [--format text|json]
```

### §7.2 Behavior

- Runs FTS in all 4 editions; aggregates by Royal-equivalent vol (uses MBU_TO_ROYAL for MBU hits).
- Output: per-Royal-vol grouping showing which editions matched and their hit counts:

```
เล่ม 19 — Samyutta Mahavagga
  ฉบับหลวง:        12 hits  (pages 257, 258, 312, ...)
  พระบาลีสยามรัฐ:   12 hits  (pages 246, ...)
  มจร.:           14 hits  (pages 309, ...)
  มมร. (vol 30+31): 13 hits combined  (vol 30 pages 412, 419; vol 31 pages 5, ...)
```

- `--limit` caps total Royal vols displayed, not per-edition.

### §7.3 Acceptance criteria

- [ ] `thera cross-ref "อริยสัจ"` produces a per-Royal-vol grouping including MBU vols correctly aggregated under their parent Royal vol.
- [ ] No MBU vol appears as a top-level group (must be folded into its Royal parent).
- [ ] If MBU-only hits exist for a Royal vol with 0 hits in other editions, that Royal vol still appears with explicit "Royal: 0 hits" line.

---

## §8 Command: `thera verify` (84000.org ground-truth diff)

### §8.1 Synopsis

```
thera verify <volume> <page> [--edition royal|mcu] [--format text|json]
```

(Pali and MBU not supported in v1 — 84000 hosts Royal and MCU.)

### §8.2 Behavior

- Fetches 84000.org for `(volume, page)` using the appropriate URL pattern. Per DESIGN_LOG §5, ~40% of vols have an unknown D-Tip ↔ 84000 page-offset → naïve `A=` param mapping is wrong for those.
- **Offset-resolution algorithm** (bundled per §14):
  1. Try `https://84000.org/tipitaka/read/r.php?B={vol}&A={page}` (TIS-620 decode, browser UA).
  2. Take ~120 chars from D-Tip Royal `(vol, page)` content as anchor.
  3. If anchor is found in fetched 84000 page → offset = 0, return diff.
  4. Else: fetch 84000 vol's index page, scan for anchor, derive offset, return diff + offset note.
  5. If anchor still not found in any 84000 page in the vol → exit 65 with "anchor not found in 84000 vol N — possible content mismatch or vol-numbering divergence".

### §8.3 Acceptance criteria

- [ ] `thera verify 1 1` returns "match" for Royal vol 1 page 1 (low-risk vol, offset=0 expected).
- [ ] `thera verify 25 1` (Khuddaka 1, known offset territory per §5) succeeds via the offset-resolution path 4 — output includes derived offset.
- [ ] Network failure exits 70 (`EX_SOFTWARE`) with message — never silently passes.
- [ ] Each verify run that derives a new offset writes a line to `data/.84000_offsets.tsv` (DEV: create `data/` if absent; format `vol\tderived_offset\ttimestamp`). This is the only "side effect" allowed. **Path lock**: `external/` is corpus-immutable per §1.5 — derived state lives in `data/`. (LOKI §16 B1.)

---

## §9 Command: `thera sikkhapada`

### §9.1 Synopsis

```
thera sikkhapada <bhikkhu|bhikkhuni> [--rule N] [--format text|json]
```

### §9.2 Behavior

- `bhikkhu` → **227 rules expected**, parsed from Royal vols 1-2 (Mahavibhanga). Parser scans the canonical text and extracts each rule by its boundary markers.
- `bhikkhuni` → **311 rules expected**, parsed from Royal vol 3 (Bhikkhuni-vibhanga) **only — literal Reading A, locked v1.0 per ARIA §26**. Vol 3 alone yields ~139 fully-stated rules; the remaining ~172 rules are referenced as bhikkhu-shared and not re-stated in vol 3. Under Reading A, that gap is real and surfaces via §9.3 R4 exit 70 + diagnostic — this is the **zero-hallucination contract working as designed**, not a parser bug.
- Default: list all rules with their citation and one-line summary derived **from the rule's own opening verbatim** (NO synthesis — first ~80 chars of the rule's body, ellipsis if truncated).
- `--rule N` returns full verbatim text of rule N.

#### §9.2.1 Reading A vs Reading B (locked v1.0; documented for v1.x reopening)

LOKI §25 surfaced a spec-interpretation ambiguity. ARIA §26 locks **Reading A** for v1.0:

- **Reading A (LOCKED v1.0)**: parse from listed source volumes only; if count < expected, exit 70 + diagnostic per §9.3 R4. Honest abstention surfaces canonical-content gaps. No synthesis. No cross-reference back-fill.
- **Reading B (v1.x backlog, NOT v1.0)**: cross-reference back-fill from bhikkhu vols 1-2 into bhikkhuni rule slots that vol 3 references but does not re-state. Requires a **canonical bhikkhuni↔bhikkhu rule-mapping artifact** (human-curated, NOT heuristic — heuristics violate §1.4 abstain>guess). Reading B implementation is its own sprint with its own LOKI verify gate. Acceptable v1.x amendment if A wants it; must NOT be retrofitted into v1.0 spec.

**Lock rationale**: Reading B for v1.0 would either (a) require a mapping artifact that doesn't exist yet (out of scope), or (b) tempt DEV to synthesize the mapping from heuristics (§1.4 violation). Reading A is the spec's literal+R4 resolution.

### §9.3 Acceptance criteria

- [ ] `thera sikkhapada bhikkhu` lists exactly 227 entries — **OR** if parser cannot extract all 227 from listed source vols, exits 70 with R4 diagnostic (no padding/truncation). Per Reading A §9.2.1, the exit-70 path is acceptance-met behavior, not failure.
- [ ] `thera sikkhapada bhikkhuni` lists exactly 311 entries — **OR** exits 70 with R4 diagnostic per Reading A §9.2.1. Bhikkhuni 311-coverage from vol 3 alone is canonically incomplete; v1.0 expects exit 70 + diagnostic + transparent gap surfacing.
- [ ] `thera sikkhapada bhikkhu --rule 1` returns Parajika 1 (sex with another being) verbatim with citation `[ฉบับหลวง เล่ม 1 หน้า X]`.
- [ ] No "summary" content beyond the literal first-N-chars-of-rule construction.
- [ ] **Hard-count enforcement (LOKI §16 R4 + ARIA §26 lock)**: if parser yields count ≠ 227 (bhikkhu) or ≠ 311 (bhikkhuni), exit 70 with diagnostic listing parsed count + missing rule numbers (first 30) + ambiguous-split locations. **Never pad/truncate to hit the target count.** Honors §1.4 abstain>guess. The exit 70 path IS the spec-correct ship state under Reading A.

(DEV: parsing logic is the new code here — Mahavibhanga structure has clear boundary markers, but expect 1-2 ambiguous splits. Edge cases tracked in implementation, escalated if >3 ambiguities surface.)

---

## §10 Command: `thera list` & `thera corpus`

### §10.1 `thera list volumes [--pitaka X] [--edition Y]`

Already implemented in cli.py. Acceptance:
- [ ] Output for default edition + no filter contains exactly 45 vol lines.
- [ ] Output for `--edition mbu` contains exactly 91 vol lines (LOKI's reverse-index headline).
- [ ] `--pitaka` filter narrows correctly using `PITAKA_BY_VOLUME` (Royal/Pali/MCU only — for MBU, filter by mapped Royal vol).

### §10.2 `thera corpus init|validate|info`

- `info`: already works (path, size, status). Acceptance: no change required.
- `init`: download + checksum-verify D-Tipitaka SQLite from kit119/D-tipitaka commit `645aa33`. Refuse to overwrite without `--force`.
- `validate`: run sanity SQL — confirm 4 tables present, row counts within ±1% of 129K total, no NULL content rows.

---

## §11 Error Model

| Exit code | Symbol | When |
|---|---|---|
| 0 | OK | Normal success |
| 1 | not-found | Valid query, no result (e.g., page beyond vol range; FTS 0 hits is exit 0) |
| 2 | usage-runtime | Bad runtime usage (unknown subcommand target, etc.) |
| 64 | EX_USAGE | Bad CLI args (out-of-range vol, empty query, malformed ref) |
| 65 | EX_DATAERR | Data-shape problem requiring user input (MBU multi-vol disambig, structural divergence detected) |
| 70 | EX_SOFTWARE | Internal failure (network, FTS extension load when explicitly required) |

DEV: import these as constants. Stable contract — LOKI tests will pin exit codes.

**Typer/click default override (LOKI §16 R2)**: typer/click default to exit code 2 for arg-validation errors. Spec demands 64 for usage errors. DEV must override — recommended pattern: custom `BadParameter` handler or explicit `raise typer.Exit(64)` inside arg validators. Do not let typer's default leak through.

---

## §12 Test Contract

### §12.1 Unit tests (in `tests/`, pytest)

For each command:
- 1 happy-path test against a fixed (vol, page) known to exist (Royal vol 1 page 1 is the universal anchor — all four editions have it, content stable).
- 1 negative test (out-of-range / not-found / wrong shape).
- 1 verbatim-contract test: read content via direct SQL, read same via CLI, assert byte-equal.

**§12.1 CLI-parser coverage (REQUIRED, post-§19.2 amendment)**: tests MUST include at least one `CliRunner.invoke(cli.app, [...])` invocation per command flag, exercising the actual typer/click parsing path. Tests that call command functions as Python functions (`cli.search(query=..., limit=...)`) supplement but do NOT replace CliRunner-level coverage. Use `runner.invoke(cli.app, [...args...], catch_exceptions=False)` so parser errors surface as test failures rather than swallowed exceptions. Rationale: typer/click version-mismatch bugs (LOKI §18 B1) only manifest at the CLI parser layer, not at the function call layer.

**§12.1 Real-corpus integration test (REQUIRED, post-§19.3 amendment by ARIA §26)**: every command that touches the corpus or external network MUST have at least one `subprocess.run` test that invokes the actual CLI binary (`python -m thera.cli ...` or installed `thera ...`) against `external/dtipitaka.db` (or, for `verify`, against the live 84000.org endpoint with `@pytest.mark.verify`) and asserts stdout byte-equals the SQL ground-truth (or, for network commands, asserts the documented exit-code behavior holds against real-world data shapes). Mocked/CliRunner tests verify parser+logic; real-corpus integration verifies that parser+logic+real-world-data-shape compose without surprises. Rationale: §18 B1 (typer/click) and §24 B1 (TIS-620 strict decoder vs 84000's byte 0xa0) both passed mocked tests but failed at the real-world data-shape boundary. Mock fixtures must include real-world bytes/data (per §24 B3) so future regressions surface in mocked path too. Apply to: search, read, compare, cross-ref, verify, sikkhapada, corpus init, corpus validate.

### §28.7 Scope (post-§31)

The §28.7 language-switcher requirement applies to the enumerated user-facing
documentation pairs only: `README.md` / `README.th.md`,
`docs/QUICKSTART.md` / `docs/QUICKSTART.th.md`,
`docs/ARCHITECTURE.md` / `docs/ARCHITECTURE.th.md`, and
`docs/USE_CASES.md` / `docs/USE_CASES.th.md`.

Contributor-internal artifacts remain outside that language-switcher scope:
`docs/CLI_SPEC.md`, `docs/corpus-mbu-volume-mapping.md`, `DESIGN_LOG.md`,
`HANDOFF.md`, `.ai-memory/HANDOFF.md`, and similar role/process memory files.
This records the narrow-read ARIA locked at DESIGN_LOG §30.2 and closes m23.

### §12.2 MBU-mapping tests (LOKI gate items)

- `to_mbu_volumes(43)` → `[88]`
- `to_mbu_volumes(25)` → `list(range(39, 48))`
- `from_mbu_volume(88)` → `43`
- `from_mbu_volume(45)` → `25`
- Round-trip: `from_mbu_volume(mbu) == royal` for every (royal, mbus) in mapping.
- **Disjoint invariant (LOKI §16 R3)**: `len(MBU_TO_ROYAL) == 91` and `len({m for ms in ROYAL_TO_MBU.values() for m in ms}) == 91`. No MBU vol may appear in two Royal lists; reverse map covers all 91 MBU vols.

### §12.3 Smoke (in `tests/smoke/`, runs against real DB if present)

- `thera read 43 1` produces ปัฏฐาน opening
- `thera read 43 1 --edition mbu` triggers the structural-divergence detector (vol 43 mbu = Dhammapada)
- `thera search "อริยสัจ" --limit 5` returns 5 hits
- `thera list volumes --edition mbu` emits 91 lines

### §12.4 84000 verify test (network-gated)

Skipped by default. Run with `pytest -m verify`. Asserts vol 1 page 1 verify returns match; vol 25 page 1 verify produces a non-zero offset.

---

## §13 Implementation Sequence (per §14 lock — `search` first)

DEV implements in this order. LOKI verifies + signs each before next starts. No parallel command streams.

1. **`thera search`** — FTS detection + fallback. Highest-leverage smoke validation. ~1-2 days.
2. Drop §3 mapping into `corpus.py` + add unit tests. <0.5 day. (Can run during/after step 1.)
3. **`thera read`** — including MBU multi-vol disambiguation. ~1 day.
4. **`thera compare`** — depends on read. ~1 day.
5. **`thera cross-ref`** — depends on search + mapping aggregation. ~1 day.
6. **`thera verify`** — including offset-resolution path. ~2 days (network + caching tsv).
7. **`thera sikkhapada`** — Mahavibhanga parsing. ~2 days (edge-case-prone).
8. `thera corpus init|validate` — download + checksum. ~1 day.

After step 6, ARIA records 84000-offset findings into DESIGN_LOG and may escalate any unmappable vols.

---

## §14 Open Questions for LOKI Review

1. **Citation format §2.1**: ARIA defaults to Arabic numerals. A might want Thai numerals (`เล่ม ๔๓ หน้า ๑`) for visual consistency with KM entries. LOKI: flag if you have an opinion.
2. **Compare ref shape §6.2**: ARIA chose `V:P:edition` literal. Alternative: `V:P --as-edition X` flag. The literal form is terser and matches existing `thera compare` stub.
3. **Sikkhapada line summary §9.2**: ARIA chose "first ~80 chars of rule body" because anything else risks synthesis. LOKI: confirm this is the cleanest verbatim path.
4. **84000 offset cache §8.2**: ARIA chose `external/.tipitaka_offsets.tsv` as the only side effect. Alternative: in-memory only. LOKI: weigh test reproducibility vs filesystem-cleanliness.

LOKI: any new flags from review go to DESIGN_LOG §15 or a new §16 — do not edit this spec inline. ARIA-DEV cycle continues from your sign-off.

---

## §15 What this spec deliberately defers

- **Performance benchmarking** — v1 must be correct, not fast. SLA is "interactive-feel for `read`/`search` against local SQLite" — measured later.
- **Caching layer** — none in v1. Each invocation opens DB cold.
- **Pretty pagination / pager** — v1 dumps all output at once; pipe to `less` if needed.
- **i18n / English UI** — v1 is Thai. CLI help strings stay Thai/English mixed as currently in cli.py.
- **Network FTS** (e.g., online cross-ref against 84000) — only `verify` touches network.
- **NotebookLM secondary path** — V2 deferred per DESIGN_LOG §13.
