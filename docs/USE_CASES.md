# Thera AI — Real-World Use Cases

> 🌏 [อ่านภาษาไทย](USE_CASES.th.md)

A CLI for querying the Pali Canon (Tipitaka) without lying, without interpretation, without paraphrase.

It pulls canonical text byte-for-byte from the source, attaches a citation `[ฉบับหลวง เล่ม X หน้า Y]`, and lets you compare 4 editions (Royal / MCU / MBU / Pali Siam) from a single command.

> **AI here is used only to retrieve, not to summarize.** The reader interprets. There is no LLM standing between you and the canonical word.

---

## Who benefits

### 🪷 Lay practitioners + meditation practitioners

You want to read the Tipitaka **literally** — not through an AI summary.

```bash
# Look up paṭiccasamuppāda (dependent origination)
thera search "ปฏิจจสมุปบาท" --limit 5

# Output:
# [ฉบับหลวง เล่ม 16 หน้า 1] ...สังขารทั้งหลายมีอวิชชาเป็นปัจจัย...
# [ฉบับหลวง เล่ม 16 หน้า 50] ...
```

Real canonical text with exact volume + page. Copy-paste straight into your study notes or citations.

### 🟠 Monastics + Pali students

You want to compare the Royal edition with the MCU edition to spot lexical differences:

```bash
thera compare 19:528 19:528:mcu

# Output: two side-by-side panels
# --- A --- [ฉบับหลวง เล่ม 19 หน้า 528]
#   ...อริยสัจ ๔ คือ...
# --- B --- [มจร. เล่ม 19 หน้า 528]
#   ...อริยสัจ ๔ ได้แก่...
```

Or check the underlying Pali phrasing:

```bash
thera read 19 528 --edition pali
# [พระบาลีสยามรัฐ เล่ม 19 หน้า 528] ...จตฺตาริ อริยสจฺจานิ...
```

### 📚 Researchers + academics

You need a verbatim quote for a paper / thesis / dissertation:

```bash
# Pull a passage as pure-source byte-for-byte
thera read 16 1 --format json > citation.json

# JSON payload's `content` field is byte-equal to the SQL row
# Paste straight into your paper's appendix
```

Need to verify your digital edition against 84000.org (the upstream ground truth)?

```bash
thera verify 1 1
# fetches 84000 live → diff → match / show offset / "anchor not found"
```

### 🟢 Buddhist knowledge-base curators (Buddhawajana-aligned KMs)

You're building a verbatim-only Buddhist KB:

```bash
# Cross-edition aggregation to surface contradictions
thera cross-ref "อนิจจัง"

# Output is grouped by Royal volume:
# เล่ม 17 — Saṃyutta-Nikāya Khandha-Vagga
#   ฉบับหลวง: 12 hits
#   มจร.: 14 hits
#   มมร. (vol 27): 13 hits
#   พระบาลีสยามรัฐ: 12 hits
```

Or pull individual training rules (sikkhāpada):

```bash
# Pārājika 1 from the bhikkhu Patimokkha
thera sikkhapada bhikkhu --rule 1
# Returns verbatim text + [ฉบับหลวง เล่ม 1 หน้า X]

# All 227 bhikkhu rules — and if Thera can't locate them all, it **does not lie**
thera sikkhapada bhikkhu
# parsed 224/227 → exit 70 + diagnostic listing rules 24, 39, 85 as missing
# (Thera will "admit it doesn't know" rather than fabricate to hit the target.)
```

### 💻 Developers + programmers

A reference implementation of the "AI that doesn't lie" pattern, transferable to other sensitive-text domains (legal corpora, scriptures of other religions, scientific documents that cannot drift):

```bash
# Every output is byte-equal to source
diff <(thera read 1 14 --format json | jq -r .content) \
     <(sqlite3 external/dtipitaka.db "SELECT content FROM thai_royal WHERE volume=1 AND page=14")
# Result: empty diff (byte-identical)
```

---

## How it differs from alternatives

| Alternative | Limitation | Thera AI |
|---|---|---|
| ChatGPT / Claude / Gemini answering canon questions | paraphrase + hallucinated citations | byte-verbatim + real citation |
| 84000.org browser | cross-edition limited to Royal + MCU | adds MBU + Pali Siam too |
| Printed Tipitaka volumes | comparing 4 editions takes serious time | instant cross-edition diff |
| Other Tipitaka apps | mostly closed-source / silently mix editions | open-source MIT + edition-honest |

---

## Try it in 5 minutes

```bash
# 1. clone
git clone https://github.com/<a's-handle>/thera.git
cd thera

# 2. install
pip install -e .

# 3. download the corpus (~555 MB; takes 2–5 minutes)
thera corpus init

# 4. first command
thera search "อริยสัจ"
```

---

## All commands (8 total)

| Command | Purpose |
|---|---|
| `thera search <query>` | Full-text search across 4 editions |
| `thera read <vol> <page>` | Read a passage verbatim |
| `thera compare <ref> <ref>` | Side-by-side comparison of two references |
| `thera cross-ref <keyword>` | Cross-edition aggregation grouped by Royal volume |
| `thera verify <vol> <page>` | Diff against 84000.org ground truth |
| `thera sikkhapada bhikkhu\|bhikkhuni [--rule N]` | Patimokkha training rules |
| `thera corpus init\|validate\|info` | Manage the local corpus |

---

## Engineering properties

- ✅ **Zero LLM in the retrieval path** — no AI summarizing, fabricating, or paraphrasing
- ✅ **Byte-equal verbatim** — output is byte-identical to the source row (verified by 7 byte-equal proofs across the test suite)
- ✅ **Edition honesty** — citations show the actual DB row's volume/page; MBU vol 88 is never silently relabeled "Royal vol 43"
- ✅ **Open-source MIT** — full code review available
- ✅ **89/91 tests pass** — structural invariants enforce that the zero-hallucination contract holds, not just nominally

---

## Known limitations (v1.0, declared honestly)

- **Bhikkhuni Patimokkha 311 rules** — Thera locates 139 from vol 3; the remaining 172 are referenced by canon as "shared with bhikkhu rules" in vols 1-2 → Thera does NOT auto-extend or fabricate; instead it surfaces the gap as a diagnostic. (Reading B planned for v1.x if a hand-curated mapping artifact is provided.)
- **`thera verify` supports only Royal + MCU** — because 84000.org hosts only those two editions
- **Aṭṭhakathā / ṭīkā (commentaries) excluded** — the project follows the Buddhawajana principle: canon only

---

## Philosophy

This project answers one question:

> *"How do you use AI with sacred text without it lying?"*

Thera's answer: **let the AI retrieve, not summarize.** The user gets what the canon **contains** — not what the AI **thinks** the canon ought to contain.

If the canon doesn't have it, Thera **does not invent it.** This honors the §1.4 abstain>guess principle: "admitting we don't know" is better than fabrication.

The intent is for this pattern to propagate to other sensitive-text domains — legal corpora, scriptures of other religions, scientific documents that cannot drift.

---

## Further reading

- Full README: [README.md](../README.md)
- Quickstart guide: [QUICKSTART.md](QUICKSTART.md)
- Architecture (for contributors): [ARCHITECTURE.md](ARCHITECTURE.md)
- Decision history (engineering): [DESIGN_LOG.md](../DESIGN_LOG.md)

---

🪷 **For practitioners — a tool that respects the Tipitaka literally.**
