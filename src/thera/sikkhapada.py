"""Sikkhapada (monastic training-rule) parser over D-Tipitaka SQLite.

Parses Vinaya Mahavibhanga (Royal vols 1-2 = bhikkhu) and Bhikkhuni-vibhanga
(Royal vol 3 = bhikkhuni) into per-rule entries with citation + verbatim
first-N-chars excerpt.

Per §1.4 + §9.3 of `docs/CLI_SPEC.md`: this module reports what it actually
finds. It does NOT pad to 227/311 nor truncate. The CLI wrapper performs the
hard-count check and exits 70 with a diagnostic when the count diverges.

Detection strategy:

    A. Numbered พระบัญญัติ markers `<global>. <local>.` at line/tab start,
       optionally followed by amendment letter (ก/ข). Captures Sanghadisesa
       through Sekhiya across both bhikkhu and bhikkhuni books.

    B. Parajika positional headings `(ปฐม|ทุติย|ตติย|จตุตถ)ปาราชิกสิกขาบท`
       resolve bhikkhu Parajika 1-4 (which use heading-only structure rather
       than `<global>. <local>.` numbering for their primary rule statement).

    C. Aniyata heading `อนิยตสิกขาบทที่ <N>` resolves bhikkhu Aniyata 1-2.

    D. Adhikaranasamatha 7 are emitted from the matikā list paragraph
       (`[๘๘๐]` for bhikkhu vol 2; `[๕๐๓]` for bhikkhuni vol 3) — split on
       the explicit ` ๑` separator that precedes each named rule.

When two pattern types yield the same global rule number, the FIRST detected
location wins (deterministic by page-ascending scan order). When a global
number is detected by no pattern, it is simply absent from the report — the
CLI surfaces this as an ambiguous gap.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Literal

Who = Literal["bhikkhu", "bhikkhuni"]

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
SUMMARY_CHARS = 80
ELLIPSIS = "…"

EXPECTED_COUNTS: dict[Who, int] = {"bhikkhu": 227, "bhikkhuni": 311}
SOURCE_VOLUMES: dict[Who, tuple[int, ...]] = {"bhikkhu": (1, 2), "bhikkhuni": (3,)}

# Pattern A — numbered พระบัญญัติ at line start.
# Allows: "๒๐.๑.", "๒๐. ๑.", "๒๑.๒. ก.", "๑๔๖. ๑", trailing dot optional after local.
NUMBERED_RULE_RE = re.compile(
    r"(?:^|\n)[\t ]*"
    r"(?P<g>[๐-๙]+)\s*\.\s*"  # noqa: RUF001
    r"(?P<l>[๐-๙]+)\s*\.?\s*"  # noqa: RUF001
    r"(?:[กข]\s*\.?\s*)?"
    r"(?=[฀-๿])",
    re.MULTILINE,
)

# Pattern B — Parajika positional headings (bhikkhu).
PARAJIKA_HEADING_RE = re.compile(
    r"(?P<pos>ปฐม|ทุติย|ตติย|จตุตถ)ปาราชิกสิกขาบท(?!\s*จบ)"
)
PARAJIKA_POSITION_TO_RULE: dict[str, int] = {
    "ปฐม": 1, "ทุติย": 2, "ตติย": 3, "จตุตถ": 4,
}

# Pattern C — Aniyata headings (bhikkhu only; rules 18-19 globally).
# D-Tipitaka renders this with optional space: `อนิยตสิกขาบทที่ ๑` or `อนิยต สิกขาบทที่ ๑`.
ANIYATA_HEADING_RE = re.compile(
    r"อนิยต\s*สิกขาบทที่\s*([๐-๙]+)(?!\s*จบ)"  # noqa: RUF001
)

# Pattern D — Adhikaranasamatha matikā paragraphs.
# Bhikkhu vol 2 has `[๘๘๐]`; bhikkhuni vol 3 has `[๕๐๓]`.
ADHIKARANA_INTRO_BHIKKHU_RE = re.compile(r"\[๘๘๐\][^\n]*")
ADHIKARANA_INTRO_BHIKKHUNI_RE = re.compile(r"\[๕๐๓\][^\n]*")

# Once we have the matikā paragraph, split on ` ๑` separator (each rule
# terminator). Names of the 7 in canonical order serve as labels only — they
# do NOT change the verbatim excerpt.
ADHIKARANASAMATHA_NAMES = (
    "สัมมุขาวินัย",
    "สติวินัย",
    "อมูฬหวินัย",
    "ปฏิญญาตกรณะ",
    "เยภุยยสิกา",
    "ตัสสปาปิยสิกา",
    "ติณวัตถารกะ",
)


@dataclass(frozen=True)
class Sikkhapada:
    """One parsed monastic training rule.

    `vol` and `page` point at the canonical Royal page where the rule's body
    or its primary heading appears — i.e. the citation stays edition-honest
    per spec §2: it reflects the row that produced the excerpt.
    """

    rule_number: int
    vol: int
    page: int
    items: str | None
    body_offset: int
    excerpt: str
    is_truncated: bool


@dataclass(frozen=True)
class ParseReport:
    rules: list[Sikkhapada]
    expected_count: int
    ambiguous_notes: list[str]
    parsed_count: int
    missing: list[int]


def _thai_int(s: str) -> int:
    return int(s.translate(THAI_DIGITS))


def _make_excerpt(body: str) -> tuple[str, bool]:
    """Return (excerpt, is_truncated). No padding; no synthesis.

    Whitespace inside the canonical body is preserved verbatim except that
    leading whitespace BEFORE the rule statement is trimmed (these are the
    line/tab indenters used for typesetting, not part of the rule itself).
    Newlines inside the excerpt window are normalized to a single space so
    the listing remains one-line per spec §9.2 ("one-line summary").
    """
    stripped = body.lstrip(" \t\r\n")
    if not stripped:
        return "", False
    # Single-line render: collapse any internal newline to a space, but keep
    # the underlying canonical bytes otherwise unchanged.
    one_line = stripped.replace("\r\n", "\n").replace("\n", " ")
    if len(one_line) <= SUMMARY_CHARS:
        return one_line, False
    return one_line[:SUMMARY_CHARS] + ELLIPSIS, True


def _scan_volume(
    conn: sqlite3.Connection,
    volume: int,
) -> list[tuple[int, str | None, str]]:
    rows = conn.execute(
        "SELECT page, items, content FROM thai_royal WHERE volume = ? ORDER BY page",
        (volume,),
    ).fetchall()
    return [(r["page"], r["items"], r["content"]) for r in rows]


def _add_first(rules: dict[int, Sikkhapada], rule: Sikkhapada) -> None:
    """First detection wins — keeps deterministic page-ascending order."""
    if rule.rule_number not in rules:
        rules[rule.rule_number] = rule


def _parse_numbered(
    rules: dict[int, Sikkhapada],
    vol: int,
    page: int,
    items: str | None,
    content: str,
    valid_range: range,
    rule_offset: int = 0,
) -> None:
    """Phase A — numbered พระบัญญัติ markers."""
    for m in NUMBERED_RULE_RE.finditer(content):
        global_num = _thai_int(m.group("g")) + rule_offset
        if global_num not in valid_range:
            continue
        body_offset = m.end()
        excerpt, is_trunc = _make_excerpt(content[body_offset:body_offset + SUMMARY_CHARS * 6])
        if not excerpt:
            continue
        _add_first(rules, Sikkhapada(global_num, vol, page, items, body_offset, excerpt, is_trunc))


def _parse_parajika_headings(
    rules: dict[int, Sikkhapada],
    vol: int,
    page: int,
    items: str | None,
    content: str,
) -> None:
    """Phase B — bhikkhu Parajika 1-4 heading-based fallback."""
    for m in PARAJIKA_HEADING_RE.finditer(content):
        rule_no = PARAJIKA_POSITION_TO_RULE[m.group("pos")]
        body_offset = m.end()
        excerpt, is_trunc = _make_excerpt(content[body_offset:body_offset + SUMMARY_CHARS * 6])
        if not excerpt:
            continue
        _add_first(rules, Sikkhapada(rule_no, vol, page, items, body_offset, excerpt, is_trunc))


def _parse_aniyata_headings(
    rules: dict[int, Sikkhapada],
    vol: int,
    page: int,
    items: str | None,
    content: str,
    rule_offset: int,
) -> None:
    """Phase C — bhikkhu Aniyata 1-2 heading fallback (global rules 18-19)."""
    for m in ANIYATA_HEADING_RE.finditer(content):
        local = _thai_int(m.group(1))
        if local not in (1, 2):
            continue
        body_offset = m.end()
        excerpt, is_trunc = _make_excerpt(content[body_offset:body_offset + SUMMARY_CHARS * 6])
        if not excerpt:
            continue
        _add_first(
            rules,
            Sikkhapada(rule_offset + local, vol, page, items, body_offset, excerpt, is_trunc),
        )


def _parse_adhikaranasamatha(
    rules: dict[int, Sikkhapada],
    pages: list[tuple[int, str | None, str]],
    intro_re: re.Pattern[str],
    rule_offset: int,
    vol: int,
) -> str | None:
    """Phase D — split the 7 Adhikaranasamatha rules out of their matikā."""
    for page, items, content in pages:
        m = intro_re.search(content)
        if m is None:
            continue
        # Rule body starts after the intro line; tail goes to end of page or
        # next blank line. The 7 rules are separated by " ๑" markers.
        tail = content[m.end():]
        # Take the first paragraph chunk up to a double newline.
        paragraph = tail.split("\n\n", 1)[0]
        # Each rule ends with " ๑" (literal Thai 1).
        chunks = re.split(r"\s+๑(?:\s|$)", paragraph)
        chunks = [c.strip() for c in chunks if c.strip()]
        if len(chunks) < 7:
            return (
                f"adhikaranasamatha matikā at vol {vol} p{page} "
                f"yielded {len(chunks)} chunks (<7)"
            )
        for idx in range(7):
            global_num = rule_offset + idx + 1
            chunk = chunks[idx]
            excerpt, is_trunc = _make_excerpt(chunk)
            if not excerpt:
                return (
                    f"adhikaranasamatha rule {idx+1} at vol {vol} p{page} "
                    "produced empty excerpt"
                )
            body_offset = content.find(chunk)
            _add_first(
                rules,
                Sikkhapada(
                    global_num, vol, page, items, max(body_offset, 0), excerpt, is_trunc,
                ),
            )
        return None
    return f"adhikaranasamatha matikā paragraph not found in vol {vol}"


def parse_sikkhapada(conn: sqlite3.Connection, who: Who) -> ParseReport:
    """Parse all training rules for one Patimokkha and return the report.

    The report's `rules` list is sorted by `rule_number` ASC. `missing` lists
    every global rule number in 1..expected that the parser did NOT locate.
    `ambiguous_notes` describes Adhikaranasamatha shape problems if any.
    """
    expected = EXPECTED_COUNTS[who]
    vols = SOURCE_VOLUMES[who]
    rules: dict[int, Sikkhapada] = {}
    ambiguous: list[str] = []

    if who == "bhikkhu":
        # 220 numbered rules (Sanghadisesa..Sekhiya) + 4 Parajika + 2 Aniyata
        # + 7 Adhikarana = 233 candidate slots, but Parajika/Aniyata may
        # overlap numbered detection — first-wins keeps citations deterministic.
        valid_numbered = range(1, 221)
        aniyata_offset = 17  # Aniyata 1 = global 18, Aniyata 2 = global 19
        adhikarana_offset = 220
        adhikarana_intro = ADHIKARANA_INTRO_BHIKKHU_RE
    else:
        # bhikkhuni vol 3: numbered range observed up to global 304 (Sekhiya 75 = 304).
        valid_numbered = range(1, 305)
        aniyata_offset = 0  # bhikkhuni has no Aniyata category
        adhikarana_offset = 304
        adhikarana_intro = ADHIKARANA_INTRO_BHIKKHUNI_RE

    all_pages: list[tuple[int, int, str | None, str]] = []
    for vol in vols:
        for page, items, content in _scan_volume(conn, vol):
            all_pages.append((vol, page, items, content))

    # Single ascending pass — first detection wins.
    for vol, page, items, content in all_pages:
        _parse_numbered(rules, vol, page, items, content, valid_numbered)
        if who == "bhikkhu" and vol == 1:
            _parse_parajika_headings(rules, vol, page, items, content)
            _parse_aniyata_headings(rules, vol, page, items, content, aniyata_offset)

    # Adhikaranasamatha tail — independent paragraph parser scoped to the
    # last source volume of this Patimokkha.
    adh_vol = vols[-1]
    adh_pages = [(p, it, c) for v, p, it, c in all_pages if v == adh_vol]
    note = _parse_adhikaranasamatha(rules, adh_pages, adhikarana_intro, adhikarana_offset, adh_vol)
    if note:
        ambiguous.append(note)

    sorted_rules = [rules[k] for k in sorted(rules)]
    missing = [n for n in range(1, expected + 1) if n not in rules]

    return ParseReport(
        rules=sorted_rules,
        expected_count=expected,
        ambiguous_notes=ambiguous,
        parsed_count=len(sorted_rules),
        missing=missing,
    )
