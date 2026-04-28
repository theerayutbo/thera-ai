"""Corpus access layer over D-Tipitaka SQLite.

All editions live in a single SQLite DB with four tables:

- thai_royal (volume, page, items, content) — primary
- thai_mcu   (volume, page, items, header, footer, display, content)
- thai_mbu   (volume, volumn_orig, page, items, content)     # typo retained from source
- pali_siam  (volume, page, items, content)                  # Pali in Thai script

FTS4+ICU virtual tables are provided by D-Tipitaka's own schema files:
- fts4 (porter tokenizer) — English-like tokenization
- fts4-icu (th_TH tokenizer) — Thai-correct tokenization (preferred)

This module is a thin, deliberately-un-clever wrapper. No caching. No AI.
Retrieval-only.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from thera.citation import EDITION_TABLES, Edition

DEFAULT_DB_PATH = Path("external/dtipitaka.db")
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")

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

_SQLITE_ICU_CANDIDATES = (
    "libsqliteicu.dylib",
    "libsqliteicu.so",
    "/opt/homebrew/lib/libsqliteicu.dylib",
    "/opt/homebrew/opt/sqlite/lib/libsqliteicu.dylib",
    "/usr/local/lib/libsqliteicu.dylib",
    "/usr/local/lib/libsqliteicu.so",
    "/usr/lib/libsqliteicu.dylib",
    "/usr/lib/libsqliteicu.so",
)


@dataclass(frozen=True)
class Passage:
    """A verbatim passage retrieved from the corpus."""
    volume: int
    page: int
    edition: Edition
    items: str | None      # D-Tipitaka "items" column — section/verse markers
    content: str


@dataclass(frozen=True)
class SearchResult(Passage):
    """A passage plus render-time match metadata for search snippets."""
    match_start: int
    match_end: int
    snippet: str
    snippet_match_start: int
    snippet_match_end: int


@dataclass(frozen=True)
class SearchBackend:
    """Search backend selected for a connection."""
    kind: str
    warning: str | None = None


def open_db(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the corpus database read-only.

    Thera never writes to the corpus. If the DB isn't present, we raise early
    rather than silently create an empty file.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Corpus DB not found at {path}. Run `thera corpus init` to set up."
        )
    # Read-only URI to protect against accidental mutation
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def read_page(
    conn: sqlite3.Connection,
    volume: int,
    page: int,
    edition: Edition = "royal",
) -> Passage | None:
    """Retrieve one (volume, page) passage verbatim. Returns None if not found."""
    table = EDITION_TABLES[edition]
    row = conn.execute(
        f"SELECT volume, page, items, content FROM {table} "
        f"WHERE volume = ? AND page = ?",
        (volume, page),
    ).fetchone()
    if row is None:
        return None
    return Passage(
        volume=row["volume"],
        page=row["page"],
        edition=edition,
        items=row["items"],
        content=row["content"],
    )


def list_volumes(conn: sqlite3.Connection, edition: Edition = "royal") -> list[int]:
    """Return sorted list of volume numbers present in the edition."""
    table = EDITION_TABLES[edition]
    rows = conn.execute(
        f"SELECT DISTINCT volume FROM {table} ORDER BY volume"
    ).fetchall()
    return [r["volume"] for r in rows]


def page_count(conn: sqlite3.Connection, volume: int, edition: Edition = "royal") -> int:
    """Number of pages in a given volume."""
    table = EDITION_TABLES[edition]
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE volume = ?",
        (volume,),
    ).fetchone()
    return int(row["n"]) if row else 0


def has_thai(text: str) -> bool:
    """Return True if text contains Thai Unicode codepoints."""
    return bool(THAI_RE.search(text))


def _fts_table_kinds(conn: sqlite3.Connection) -> dict[str, str]:
    """Inspect loaded tables and classify FTS4 variants by edition table name."""
    rows = conn.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table'
          AND (
            name LIKE 'fts4%'
            OR lower(coalesce(sql, '')) LIKE '%using fts4%'
          )
        """
    ).fetchall()
    kinds: dict[str, str] = {}
    for row in rows:
        sql = (row["sql"] or "").lower()
        name = row["name"]
        if "using fts4" not in sql and not name.startswith("fts4"):
            continue
        kinds[name] = "fts4-icu" if "tokenize=icu" in sql else "fts4"
    return kinds


def _try_load_sqlite_icu(conn: sqlite3.Connection) -> bool:
    """Best-effort load of SQLite ICU extension. Failure is a normal fallback path."""
    try:
        conn.enable_load_extension(True)
    except (AttributeError, sqlite3.Error):
        return False
    try:
        for candidate in _SQLITE_ICU_CANDIDATES:
            try:
                conn.load_extension(candidate)
                return True
            except sqlite3.Error:
                continue
    finally:
        with suppress(sqlite3.Error):
            conn.enable_load_extension(False)
    return False


def detect_search_backend(conn: sqlite3.Connection, edition: Edition, query: str) -> SearchBackend:
    """Select FTS4/FTS4-ICU when available, otherwise declare LIKE fallback."""
    table = EDITION_TABLES[edition]
    kinds = _fts_table_kinds(conn)
    if table in kinds:
        kind = kinds[table]
        if has_thai(query) and kind == "fts4-icu":
            return SearchBackend(kind)
        if not has_thai(query) or kind == "fts4":
            return SearchBackend(kind)

    _try_load_sqlite_icu(conn)
    kinds = _fts_table_kinds(conn)
    if table in kinds:
        kind = kinds[table]
        if has_thai(query) and kind == "fts4-icu":
            return SearchBackend(kind)
        if not has_thai(query) or kind == "fts4":
            return SearchBackend(kind)

    return SearchBackend("like", "[fallback: linear scan, slow]")


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _snippet_for(
    content: str,
    query: str,
    radius: int = 80,
) -> tuple[int, int, str, int, int] | None:
    start = content.find(query)
    if start == -1:
        folded_content = content.casefold()
        folded_query = query.casefold()
        start = folded_content.find(folded_query)
        if start == -1:
            return None
    end = start + len(query)
    snippet_start = max(0, start - radius)
    snippet_end = min(len(content), end + radius)
    snippet = content[snippet_start:snippet_end]
    return start, end, snippet, start - snippet_start, end - snippet_start


def _search_sql(backend: SearchBackend, table: str) -> str:
    if backend.kind.startswith("fts4"):
        return (
            f"SELECT volume, page, items, content FROM {table} "
            "WHERE content MATCH ? ORDER BY volume ASC, page ASC LIMIT ?"
        )
    return (
        f"SELECT volume, page, items, content FROM {table} "
        "WHERE content LIKE ? ESCAPE '\\' ORDER BY volume ASC, page ASC LIMIT ?"
    )

def fts_search(
    conn: sqlite3.Connection,
    query: str,
    edition: Edition = "royal",
    limit: int = 50,
) -> tuple[list[SearchResult], SearchBackend, bool]:
    """Search one edition and return (results, backend, truncated)."""
    backend = detect_search_backend(conn, edition, query)
    table = EDITION_TABLES[edition]
    param = query if backend.kind.startswith("fts4") else _like_pattern(query)
    rows = conn.execute(_search_sql(backend, table), (param, limit + 1)).fetchall()
    truncated = len(rows) > limit
    results: list[SearchResult] = []
    for row in rows[:limit]:
        content = row["content"]
        snippet_data = _snippet_for(content, query)
        if snippet_data is None:
            snippet_data = (0, 0, content[:160], 0, 0)
        match_start, match_end, snippet, snippet_match_start, snippet_match_end = snippet_data
        results.append(
            SearchResult(
                volume=row["volume"],
                page=row["page"],
                edition=edition,
                items=row["items"],
                content=content,
                match_start=match_start,
                match_end=match_end,
                snippet=snippet,
                snippet_match_start=snippet_match_start,
                snippet_match_end=snippet_match_end,
            )
        )
    return results, backend, truncated
