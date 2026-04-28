"""Bootstrap and validate the local D-Tipitaka SQLite corpus.

Per spec §10.2 — `thera corpus init` and `thera corpus validate`.

`init` prefers vendored `.sql.bz2` dumps under `vendor/D-tipitaka/1.2/`,
falls back to downloading the same files from kit119/D-tipitaka commit
`645aa33`, verifies SHA-256 checksums against a pinned manifest, and builds
`external/dtipitaka.db` by streaming the decompressed SQL into sqlite3.
**`external/dtipitaka.db` is the ONLY mutation that `init` performs.** Per
DESIGN_LOG §17 lock, derived state (caches, offsets) lives under `data/`,
not `external/`.

`validate` runs sanity SQL against an existing DB: confirms the four
expected tables are present, total row count is within ±1% of the pinned
expected count (129,147 rows for commit 645aa33), and no `content` rows
are NULL.

Network calls are isolated behind a small `Fetcher` callable so tests can
inject a deterministic in-memory fixture without touching the real network.
"""

from __future__ import annotations

import bz2
import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

UPSTREAM_REPO = "https://github.com/kit119/D-tipitaka"
UPSTREAM_COMMIT = "645aa33"
UPSTREAM_RAW_BASE = (
    f"https://raw.githubusercontent.com/kit119/D-tipitaka/{UPSTREAM_COMMIT}/1.2"
)
VENDOR_SOURCE_DIR = Path("vendor/D-tipitaka/1.2")
VENDOR_MANIFEST_PATH = VENDOR_SOURCE_DIR / "UPSTREAM_FILES"

# SHA-256 manifest of upstream files vendored from commit 645aa33.
# The four `.sql.bz2` files are load-bearing for corpus build. README.TXT is
# bundled for attribution and checked by LOKI against upstream.
UPSTREAM_FILES: dict[str, str] = {
    "pali_siam.sql.bz2":  "f0b5a644f30c030077543ce396f49921a52ef6f545b9fb177a1d6cb8576f4540",
    "thai_mbu.sql.bz2":   "d464c28b31e61576a57b6e5a2bac2e635300aa52fc8755936c120f7036248b2f",
    "thai_mcu.sql.bz2":   "27b5031fdd3dc1cf9cdc16728a984f7251302f53a52cf603b768124c01ff8e65",
    "thai_royal.sql.bz2": "1c6d13442215902dec64527fa6c88cdfeee30cd2fc6d81d730fc10592b7569f2",
    "README.TXT":         "f56bdef46d6bf91ad105beb7ff663e0300c0f8b5e17e2c4fbf88765c864f458d",
}
CORPUS_DUMP_FILES: tuple[str, ...] = (
    "pali_siam.sql.bz2",
    "thai_mbu.sql.bz2",
    "thai_mcu.sql.bz2",
    "thai_royal.sql.bz2",
)

EXPECTED_TABLES: tuple[str, ...] = ("pali_siam", "thai_mbu", "thai_mcu", "thai_royal")

# Per-table row counts at commit 645aa33 (cumulative = 129,147). Validate
# checks total against ±1% per spec §10.2; per-table values are recorded for
# diagnostic context.
EXPECTED_ROW_COUNTS: dict[str, int] = {
    "thai_royal": 19_697,
    "thai_mcu":   25_155,
    "thai_mbu":   62_380,
    "pali_siam":  21_915,
}
EXPECTED_TOTAL_ROWS: int = sum(EXPECTED_ROW_COUNTS.values())  # 129,147
ROW_COUNT_TOLERANCE: float = 0.01  # ±1% per spec §10.2

DOWNLOAD_TIMEOUT_SECONDS = 60
USER_AGENT = "thera-corpus-init/1.0 (+https://github.com/aegiszero/thera)"


class CorpusSetupError(Exception):
    """Bootstrap / validate failed: network, checksum, decompress, or shape."""


class CorpusAlreadyExistsError(CorpusSetupError):
    """Target corpus already exists and `--force` was not requested."""


@dataclass(frozen=True)
class ValidateReport:
    tables_present: list[str]
    tables_missing: list[str]
    row_counts: dict[str, int]
    total_rows: int
    null_content_counts: dict[str, int]
    ok: bool
    errors: list[str] = field(default_factory=list)


# A fetcher accepts a URL and returns the file payload as bytes. Tests inject
# a deterministic mapping; production uses urllib.
Fetcher = Callable[[str], bytes]
ProgressCallback = Callable[[str], None]


def _default_fetcher(url: str) -> bytes:
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _verify_payload(filename: str, payload: bytes) -> None:
    expected_sha = UPSTREAM_FILES[filename]
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha:
        raise CorpusSetupError(
            f"checksum mismatch for {filename}: expected {expected_sha}, got {digest}"
        )


def _load_vendor_payloads(progress: ProgressCallback | None = None) -> dict[str, bytes] | None:
    payloads: dict[str, bytes] = {}
    for filename in CORPUS_DUMP_FILES:
        path = VENDOR_SOURCE_DIR / filename
        if not path.exists():
            _emit(progress, f"vendor source missing: {path}; falling back to network")
            return None
        try:
            payload = path.read_bytes()
            _verify_payload(filename, payload)
        except CorpusSetupError as exc:
            _emit(progress, f"vendor source invalid: {exc}; falling back to network")
            return None
        except OSError as exc:
            _emit(progress, f"vendor source unreadable: {path}: {exc}; falling back to network")
            return None
        payloads[filename] = payload
    _emit(progress, f"using vendored corpus sources from {VENDOR_SOURCE_DIR}")
    return payloads


def _fetch_network_payloads(
    fetcher: Fetcher,
    progress: ProgressCallback | None = None,
) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for filename in CORPUS_DUMP_FILES:
        url = f"{UPSTREAM_RAW_BASE}/{filename}"
        _emit(progress, f"downloading {filename} from {url}")
        try:
            payload = fetcher(url)
        except CorpusSetupError:
            raise
        except Exception as exc:
            raise CorpusSetupError(f"download failed for {filename}: {exc}") from exc
        _verify_payload(filename, payload)
        _emit(progress, f"  checksum OK ({UPSTREAM_FILES[filename][:12]}...)")
        payloads[filename] = payload
    return payloads


def init_corpus(
    target_path: Path,
    *,
    force: bool = False,
    fetcher: Fetcher | None = None,
    progress: ProgressCallback | None = None,
) -> None:
    """Download, verify, and build the local corpus DB at `target_path`.

    Raises `CorpusSetupError` for any failure mode (existing-file gate,
    network, checksum mismatch, decompression, or SQL import).
    """
    if target_path.exists() and not force:
        raise CorpusAlreadyExistsError(
            f"corpus already exists at {target_path}; pass --force to overwrite"
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, bytes] | None = None
    if fetcher is None:
        payloads = _load_vendor_payloads(progress)
        fetcher = _default_fetcher
    if payloads is None:
        payloads = _fetch_network_payloads(fetcher, progress)

    decompressed_chunks: list[bytes] = []
    for filename in CORPUS_DUMP_FILES:
        try:
            decompressed_chunks.append(bz2.decompress(payloads[filename]))
        except OSError as exc:
            raise CorpusSetupError(f"failed to decompress {filename}: {exc}") from exc

    # Order is deterministic (insertion order on UPSTREAM_FILES) and matches
    # the README's `cat *.sql.bz2 | bunzip2 | sqlite3 dtipitaka.db` recipe.
    sql_script = b"".join(decompressed_chunks).decode("utf-8")

    if target_path.exists():
        target_path.unlink()
    _emit(progress, f"importing into {target_path}")

    conn = sqlite3.connect(target_path)
    try:
        conn.executescript(sql_script)
        conn.commit()
    finally:
        conn.close()

    _emit(progress, "init complete")


def validate_corpus(conn: sqlite3.Connection) -> ValidateReport:
    """Run sanity SQL against an existing corpus and return a report.

    Checks per spec §10.2:
      - 4 expected tables present
      - cumulative row count within ±1% of EXPECTED_TOTAL_ROWS
      - no NULL content rows in any of the 4 tables
    """
    actual_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    tables_present = sorted(t for t in EXPECTED_TABLES if t in actual_tables)
    tables_missing = sorted(t for t in EXPECTED_TABLES if t not in actual_tables)

    errors: list[str] = []
    if tables_missing:
        errors.append(f"missing tables: {tables_missing}")

    row_counts: dict[str, int] = {}
    null_content_counts: dict[str, int] = {}
    for table in tables_present:
        row_counts[table] = int(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
        null_content_counts[table] = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE content IS NULL"
            ).fetchone()[0]
        )

    total_rows = sum(row_counts.values())
    if tables_present and EXPECTED_TOTAL_ROWS > 0:
        delta_fraction = abs(total_rows - EXPECTED_TOTAL_ROWS) / EXPECTED_TOTAL_ROWS
        if delta_fraction > ROW_COUNT_TOLERANCE:
            errors.append(
                f"total row count {total_rows} outside ±"
                f"{ROW_COUNT_TOLERANCE * 100:.0f}% of expected "
                f"{EXPECTED_TOTAL_ROWS} (delta={delta_fraction:.4%})"
            )

    for table, n_null in null_content_counts.items():
        if n_null > 0:
            errors.append(f"{table} has {n_null} NULL content rows")

    return ValidateReport(
        tables_present=tables_present,
        tables_missing=tables_missing,
        row_counts=row_counts,
        total_rows=total_rows,
        null_content_counts=null_content_counts,
        ok=not errors,
        errors=errors,
    )
