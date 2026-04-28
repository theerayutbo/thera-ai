"""§10.2 + §19.2 + §19.3 — `thera corpus init|validate` tests.

Mocked fetcher cases use REAL bz2 payloads sourced from
`external/D-tipitaka/1.2/*.sql.bz2` per §24 B3 (mock fixtures must include
real-world bytes so future regressions surface in mocked path too).

Real-corpus integration uses `subprocess.run` against the actual
`thera corpus validate` CLI binary per §12.1 (§19.3 amendment by ARIA §26).
"""

from __future__ import annotations

import bz2
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import thera.cli as cli
from thera.corpus_setup import (
    CORPUS_DUMP_FILES,
    EXPECTED_TOTAL_ROWS,
    UPSTREAM_FILES,
    UPSTREAM_RAW_BASE,
    VENDOR_MANIFEST_PATH,
    VENDOR_SOURCE_DIR,
    CorpusAlreadyExistsError,
    CorpusSetupError,
    init_corpus,
    validate_corpus,
)

DB_PATH = Path("external/dtipitaka.db")
SOURCE_DIR = Path("external/D-tipitaka/1.2")
TMP_SOURCE_DIR = Path("/tmp")
runner = CliRunner()


def _have_real_source_dumps() -> bool:
    return all(_payload_path(name) is not None for name in CORPUS_DUMP_FILES)


def _payload_path(name: str) -> Path | None:
    """Return a readable pinned dump path.

    OneDrive may leave `external/D-tipitaka` entries as dataless placeholders.
    Prefer hydrated `/tmp` downloads when present; otherwise require a local
    source file to be readable before treating the fixture as available.
    """
    for base in (TMP_SOURCE_DIR, SOURCE_DIR):
        path = base / name
        if not path.exists():
            continue
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            continue
        return path
    return None


def _real_payloads() -> dict[str, bytes]:
    """Read the four pinned `.sql.bz2` payloads from the local upstream clone."""
    payloads: dict[str, bytes] = {}
    for name in CORPUS_DUMP_FILES:
        path = _payload_path(name)
        if path is None:
            raise OSError(f"{name} is not readable from {SOURCE_DIR} or {TMP_SOURCE_DIR}")
        payloads[name] = path.read_bytes()
    return payloads


def _make_fetcher(payloads: dict[str, bytes]):
    def _fetcher(url: str) -> bytes:
        for filename, data in payloads.items():
            if url == f"{UPSTREAM_RAW_BASE}/{filename}":
                return data
        raise AssertionError(f"unexpected fetch URL: {url}")

    return _fetcher


def _synthetic_payloads(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Small checksum-pinned corpus payloads for fast CliRunner init tests."""
    sql_by_file = {
        "pali_siam.sql.bz2": (
            "CREATE TABLE pali_siam "
            "(volume INT, page INT, items TEXT, content TEXT);"
            "INSERT INTO pali_siam VALUES (1, 1, NULL, 'pali');"
        ),
        "thai_mbu.sql.bz2": (
            "CREATE TABLE thai_mbu "
            "(volume INT, volumn_orig INT, page INT, items TEXT, content TEXT);"
            "INSERT INTO thai_mbu VALUES (1, 1, 1, NULL, 'mbu');"
        ),
        "thai_mcu.sql.bz2": (
            "CREATE TABLE thai_mcu "
            "(volume INT, page INT, items TEXT, header TEXT, footer TEXT, "
            "display TEXT, content TEXT);"
            "INSERT INTO thai_mcu VALUES (1, 1, NULL, NULL, NULL, NULL, 'mcu');"
        ),
        "thai_royal.sql.bz2": (
            "CREATE TABLE thai_royal "
            "(volume INT, page INT, items TEXT, content TEXT);"
            "INSERT INTO thai_royal VALUES (1, 1, NULL, 'royal');"
        ),
    }
    payloads = {
        name: bz2.compress(sql.encode("utf-8"))
        for name, sql in sql_by_file.items()
    }
    monkeypatch.setattr(
        "thera.corpus_setup.UPSTREAM_FILES",
        {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
    )
    return payloads


@pytest.fixture
def real_payloads() -> dict[str, bytes]:
    if not _have_real_source_dumps():
        pytest.skip(
            f"upstream `.sql.bz2` clone not present under {SOURCE_DIR}; "
            "init integration test requires the local D-Tipitaka mirror"
        )
    return _real_payloads()


@pytest.mark.corpus
def test_init_builds_corpus_from_real_bz2_payloads(
    real_payloads: dict[str, bytes],
    tmp_path: Path,
) -> None:
    """§19.3 mock fixture uses REAL byte payloads — exercises decompress + import
    against the actual upstream data shape rather than synthetic SQL."""
    target = tmp_path / "dtipitaka.db"
    fetcher = _make_fetcher(real_payloads)

    progress: list[str] = []
    init_corpus(target, fetcher=fetcher, progress=progress.append)

    assert target.exists()
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
    finally:
        conn.close()

    assert report.ok, f"validate failed after init: {report.errors}"
    assert sorted(report.tables_present) == ["pali_siam", "thai_mbu", "thai_mcu", "thai_royal"]
    assert report.total_rows == EXPECTED_TOTAL_ROWS
    # Progress callback received per-file download + checksum + import lines.
    assert any("downloading pali_siam.sql.bz2" in line for line in progress)
    assert any("checksum OK" in line for line in progress)
    assert any("init complete" in line for line in progress)


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "dtipitaka.db"
    target.write_bytes(b"sentinel")
    sentinel_size = target.stat().st_size

    with pytest.raises(CorpusAlreadyExistsError, match="already exists"):
        init_corpus(target, fetcher=lambda _url: b"unused")

    # Sentinel intact — no clobber.
    assert target.read_bytes() == b"sentinel"
    assert target.stat().st_size == sentinel_size


@pytest.mark.corpus
def test_init_with_force_replaces_existing(
    real_payloads: dict[str, bytes],
    tmp_path: Path,
) -> None:
    target = tmp_path / "dtipitaka.db"
    target.write_bytes(b"sentinel-bytes")
    fetcher = _make_fetcher(real_payloads)

    init_corpus(target, force=True, fetcher=fetcher)

    assert target.stat().st_size > 100_000_000  # real corpus is hundreds of MB
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
    finally:
        conn.close()
    assert report.ok


def test_init_checksum_mismatch_aborts(tmp_path: Path) -> None:
    target = tmp_path / "dtipitaka.db"
    bad_payloads = {name: b"corrupt-bytes" for name in UPSTREAM_FILES}

    with pytest.raises(CorpusSetupError, match="checksum mismatch"):
        init_corpus(target, fetcher=_make_fetcher(bad_payloads))

    assert not target.exists()


def test_init_network_failure_propagates_as_setup_error(tmp_path: Path) -> None:
    target = tmp_path / "dtipitaka.db"

    def _failing_fetcher(_url: str) -> bytes:
        from urllib.error import URLError

        raise URLError("simulated network failure")

    with pytest.raises(CorpusSetupError, match="download failed"):
        init_corpus(target, fetcher=_failing_fetcher)

    assert not target.exists()


def test_corpus_init_cli_builds_fresh_target_with_pinned_checksums(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """§19.2 — init happy path through Typer parser, using checksum-pinned bytes."""
    target = tmp_path / "external" / "dtipitaka.db"
    payloads = _synthetic_payloads(monkeypatch)
    monkeypatch.setattr(cli, "DEFAULT_DB_PATH", target)
    monkeypatch.setattr("thera.corpus_setup.VENDOR_SOURCE_DIR", tmp_path / "absent-vendor")
    monkeypatch.setattr(
        "thera.corpus_setup._default_fetcher",
        _make_fetcher(payloads),
    )

    result = runner.invoke(cli.app, ["corpus", "init"], catch_exceptions=False)

    assert result.exit_code == 0, result.stderr
    assert "corpus initialized" in result.output
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert tables == {"pali_siam", "thai_mbu", "thai_mcu", "thai_royal"}


def test_corpus_init_cli_force_overwrites_existing_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """§19.2 — --force reaches the clean overwrite path through CliRunner."""
    target = tmp_path / "external" / "dtipitaka.db"
    target.parent.mkdir()
    target.write_bytes(b"sentinel")
    payloads = _synthetic_payloads(monkeypatch)
    monkeypatch.setattr(cli, "DEFAULT_DB_PATH", target)
    monkeypatch.setattr("thera.corpus_setup.VENDOR_SOURCE_DIR", tmp_path / "absent-vendor")
    monkeypatch.setattr(
        "thera.corpus_setup._default_fetcher",
        _make_fetcher(payloads),
    )

    result = runner.invoke(cli.app, ["corpus", "init", "--force"], catch_exceptions=False)

    assert result.exit_code == 0, result.stderr
    assert target.read_bytes() != b"sentinel"
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT content FROM thai_royal").fetchone()[0] == "royal"
    finally:
        conn.close()


def test_corpus_init_cli_network_failure_exits_70(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """§11 + §19.2 — mocked URLError during init maps to EX_SOFTWARE."""
    from urllib.error import URLError

    target = tmp_path / "external" / "dtipitaka.db"
    monkeypatch.setattr(cli, "DEFAULT_DB_PATH", target)
    monkeypatch.setattr("thera.corpus_setup.VENDOR_SOURCE_DIR", tmp_path / "absent-vendor")

    def _fail(_url: str) -> bytes:
        raise URLError("offline")

    monkeypatch.setattr("thera.corpus_setup._default_fetcher", _fail)

    result = runner.invoke(cli.app, ["corpus", "init"], catch_exceptions=False)

    assert result.exit_code == 70
    assert "download failed" in result.stderr
    assert not target.exists()


@pytest.mark.corpus
def test_init_does_not_write_outside_target_path(
    real_payloads: dict[str, bytes],
    tmp_path: Path,
) -> None:
    """§17 path discipline — init must not touch `data/` or any sibling files."""
    target = tmp_path / "external" / "dtipitaka.db"
    fetcher = _make_fetcher(real_payloads)

    init_corpus(target, fetcher=fetcher)

    sibling_paths = list(tmp_path.rglob("*"))
    expected = {target, target.parent}
    unexpected = [p for p in sibling_paths if p not in expected and p.is_file()]
    assert not unexpected, f"init produced unexpected files: {unexpected}"


def test_validate_against_real_db_returns_ok() -> None:
    if not DB_PATH.exists():
        pytest.skip(f"real corpus not present at {DB_PATH}")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
    finally:
        conn.close()

    assert report.ok, f"unexpected validate errors: {report.errors}"
    assert sorted(report.tables_present) == ["pali_siam", "thai_mbu", "thai_mcu", "thai_royal"]
    assert report.total_rows == EXPECTED_TOTAL_ROWS
    assert all(n == 0 for n in report.null_content_counts.values())


def test_validate_detects_missing_table(tmp_path: Path) -> None:
    target = tmp_path / "partial.db"
    conn = sqlite3.connect(target)
    try:
        conn.executescript(
            "CREATE TABLE thai_royal (volume INT, page INT, items TEXT, content TEXT);"
            "INSERT INTO thai_royal VALUES (1, 1, NULL, 'verbatim');"
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
    finally:
        conn.close()

    assert not report.ok
    assert "missing tables" in " ".join(report.errors)
    assert sorted(report.tables_missing) == ["pali_siam", "thai_mbu", "thai_mcu"]


def test_validate_detects_null_content(tmp_path: Path) -> None:
    target = tmp_path / "nullcontent.db"
    conn = sqlite3.connect(target)
    mbu_schema = (
        "CREATE TABLE thai_mbu "
        "(volume INT, volumn_orig INT, page INT, items TEXT, content TEXT);"
    )
    try:
        conn.executescript(
            "CREATE TABLE thai_royal (volume INT, page INT, items TEXT, content TEXT);"
            "CREATE TABLE thai_mcu (volume INT, page INT, items TEXT, content TEXT);"
            + mbu_schema
            + "CREATE TABLE pali_siam (volume INT, page INT, items TEXT, content TEXT);"
            "INSERT INTO thai_royal VALUES (1, 1, '[1]', NULL);"
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
    finally:
        conn.close()

    assert not report.ok
    assert any("NULL content" in err for err in report.errors)


def test_corpus_validate_cli_against_real_db_exits_0() -> None:
    """§19.2 + §19.3 — CliRunner against real DB."""
    if not DB_PATH.exists():
        pytest.skip(f"real corpus not present at {DB_PATH}")

    result = runner.invoke(cli.app, ["corpus", "validate"], catch_exceptions=False)

    assert result.exit_code == 0, f"stderr={result.stderr!r}"
    assert "thai_royal: 19697 rows" in result.output
    assert "validate OK" in result.output


def test_corpus_validate_subprocess_against_real_db() -> None:
    """§19.3 informal — subprocess shell-out hitting the real corpus."""
    if not DB_PATH.exists():
        pytest.skip(f"real corpus not present at {DB_PATH}")

    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}
    result = subprocess.run(
        [sys.executable, "-m", "thera.cli", "corpus", "validate"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert f"total: {EXPECTED_TOTAL_ROWS} rows" in result.stdout
    assert "validate OK" in result.stdout


def test_corpus_init_cli_refuses_overwrite_without_force() -> None:
    """§19.2 — existing-corpus gate via CliRunner; no real network/DB touch."""
    # Real DB is present at default path; running init without --force must abort.
    if not DB_PATH.exists():
        pytest.skip(f"real corpus not present at {DB_PATH} — gate test needs an existing file")

    result = runner.invoke(cli.app, ["corpus", "init"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "already exists" in result.stderr
    assert "--force" in result.stderr


def test_corpus_unknown_action_exits_64() -> None:
    result = runner.invoke(cli.app, ["corpus", "rebuild"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "Unknown corpus action" in result.output


def test_corpus_validate_when_db_missing_exits_64(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "DEFAULT_DB_PATH", tmp_path / "absent.db")

    result = runner.invoke(cli.app, ["corpus", "validate"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "corpus DB missing" in result.stderr


def test_upstream_manifest_pins_four_files_with_sha256() -> None:
    """Manifest invariant: 4 dumps + README.TXT, all with SHA-256 hashes."""
    assert set(UPSTREAM_FILES) == {
        "pali_siam.sql.bz2",
        "thai_mbu.sql.bz2",
        "thai_mcu.sql.bz2",
        "thai_royal.sql.bz2",
        "README.TXT",
    }
    for filename, sha in UPSTREAM_FILES.items():
        assert len(sha) == 64, f"{filename} sha length {len(sha)} != 64"
        assert all(c in "0123456789abcdef" for c in sha), f"{filename} sha not hex"


def test_vendor_manifest_matches_code_manifest() -> None:
    if not VENDOR_MANIFEST_PATH.exists():
        pytest.skip(f"vendor manifest not present at {VENDOR_MANIFEST_PATH}")

    manifest: dict[str, str] = {}
    for line in VENDOR_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        sha, filename = line.split(maxsplit=1)
        manifest[filename] = sha

    assert manifest == UPSTREAM_FILES


@pytest.mark.corpus
def test_upstream_files_match_local_clone_when_present() -> None:
    """When the local D-Tipitaka clone is on disk, its SHA-256s must match the
    pinned manifest — guards against silent drift between repo and code."""
    if not _have_real_source_dumps():
        pytest.skip(f"upstream clone not present under {SOURCE_DIR}")
    import hashlib

    for filename in CORPUS_DUMP_FILES:
        expected_sha = UPSTREAM_FILES[filename]
        path = _payload_path(filename)
        assert path is not None
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_sha, (
            f"{filename}: clone sha {actual} != pinned manifest {expected_sha}"
        )


def test_init_uses_local_vendor_when_present(tmp_path: Path) -> None:
    """v1.1 default path: local vendor builds a DB and subprocess output is byte-equal."""
    if not all((VENDOR_SOURCE_DIR / name).exists() for name in CORPUS_DUMP_FILES):
        pytest.skip(f"vendored corpus files not present under {VENDOR_SOURCE_DIR}")

    target = tmp_path / "external" / "dtipitaka.db"

    init_corpus(target, fetcher=None)
    assert target.exists()

    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        report = validate_corpus(conn)
        items, content = conn.execute(
            "SELECT items, content FROM thai_royal WHERE volume = 1 AND page = 1"
        ).fetchone()
    finally:
        conn.close()

    assert report.ok, report.errors
    assert report.total_rows == EXPECTED_TOTAL_ROWS

    env = {
        **os.environ,
        "PYTHONPATH": str(Path("src").resolve()),
        "THERA_DB_PATH": str(target),
    }
    result = subprocess.run(
        [sys.executable, "-m", "thera.cli", "read", "1", "1"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    expected_stdout = f"[ฉบับหลวง เล่ม 1 หน้า 1]\n{items}\n\n{content}"
    if not expected_stdout.endswith("\n"):
        expected_stdout += "\n"
    assert result.stdout == expected_stdout
