from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from typer.testing import CliRunner

import thera.cli as cli
from thera.corpus import SearchBackend, detect_search_backend, fts_search

runner = CliRunner()


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        for table in ("thai_royal", "thai_mcu", "thai_mbu", "pali_siam"):
            conn.execute(f"CREATE TABLE {table} (volume INT, page INT, items TEXT, content TEXT)")
        conn.executemany(
            "INSERT INTO thai_royal VALUES (?, ?, ?, ?)",
            [
                (1, 1, "1", "alpha อนิจจัง beta"),
                (1, 2, "2", "gamma อนิจจัง delta"),
                (2, 1, "3", "no match here"),
            ],
        )
        conn.execute("INSERT INTO thai_mcu VALUES (1, 1, '1', 'mcu ปฏิจจสมุปบาท')")
        conn.execute("INSERT INTO thai_mbu VALUES (1, 1, '1', 'mbu ปฏิจจสมุปบาท')")
        conn.execute("INSERT INTO pali_siam VALUES (1, 1, '1', 'pali ปฏิจจสมุปบาท')")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _open_test_db(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def test_search_like_fallback_limit_and_truncation(tmp_path: Path) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    with _open_test_db(db) as conn:
        results, backend, truncated = fts_search(conn, "อนิจจัง", "royal", 1)

    assert backend == SearchBackend("like", "[fallback: linear scan, slow]")
    assert truncated is True
    assert len(results) == 1
    assert results[0].volume == 1
    assert results[0].page == 1
    assert "อนิจจัง" in results[0].snippet


def test_search_cli_rejects_empty_query() -> None:
    result = runner.invoke(cli.app, ["search", ""], catch_exceptions=False)

    assert result.exit_code == 64
    assert "empty query rejected" in result.stderr


def test_search_cli_limit_flag_and_truncation_via_parser(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    result = runner.invoke(
        cli.app,
        ["search", "อนิจจัง", "--limit", "1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" in result.output
    assert "[ฉบับหลวง เล่ม 1 หน้า 2]" not in result.output
    assert "[truncated at 1" in result.output


def test_search_cli_format_json_flag_via_parser(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    result = runner.invoke(
        cli.app,
        ["search", "อนิจจัง", "--format", "json", "--limit", "1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["citation"]["edition"] == "royal"
    assert payload["content"] == "alpha อนิจจัง beta"
    assert json.loads(lines[1]) == {"notice": "[truncated at 1 — use --limit to expand]"}


def test_search_cli_edition_all_flag_via_parser(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    result = runner.invoke(
        cli.app,
        ["search", "ปฏิจจสมุปบาท", "--edition", "all", "--limit", "1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[มจร. เล่ม 1 หน้า 1]" in result.output
    assert "[มมร. เล่ม 1 หน้า 1]" in result.output
    assert "[พระบาลีสยามรัฐ เล่ม 1 หน้า 1]" in result.output
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" not in result.output


def test_search_cli_edition_pali_flag_via_parser(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    result = runner.invoke(
        cli.app,
        ["search", "ปฏิจจสมุปบาท", "--edition", "pali"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[พระบาลีสยามรัฐ เล่ม 1 หน้า 1]" in result.output
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" not in result.output


def test_search_cli_limit_zero_exits_64_via_parser() -> None:
    result = runner.invoke(
        cli.app,
        ["search", "อนิจจัง", "--limit", "0"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64
    assert "limit must be >= 1" in result.stderr


def test_search_cli_bad_limit_type_exits_64_via_click_handler() -> None:
    result = runner.invoke(
        cli.app,
        ["search", "อนิจจัง", "--limit", "notanint"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64


def test_search_cli_json_lines_are_well_formed_and_verbatim(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    cli.search("อนิจจัง", limit=1, output_format="json")

    lines = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["citation"]["edition"] == "royal"
    assert payload["content"] == "alpha อนิจจัง beta"
    assert json.loads(lines[1]) == {"notice": "[truncated at 1 — use --limit to expand]"}


def test_search_all_groups_editions_without_citation_contamination(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db = tmp_path / "corpus.db"
    _make_db(db)
    monkeypatch.setattr(cli, "open_db", lambda: _open_test_db(db))

    cli.search("ปฏิจจสมุปบาท", edition="all", limit=1)

    stdout = capsys.readouterr().out
    assert "[มจร. เล่ม 1 หน้า 1]" in stdout
    assert "[มมร. เล่ม 1 หน้า 1]" in stdout
    assert "[พระบาลีสยามรัฐ เล่ม 1 หน้า 1]" in stdout
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" not in stdout


def test_detect_search_backend_distinguishes_fts4(tmp_path: Path) -> None:
    db = tmp_path / "fts.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE VIRTUAL TABLE thai_royal USING fts4(volume, page, items, content)")
        conn.commit()
        assert detect_search_backend(conn, "royal", "anicca").kind == "fts4"
    finally:
        conn.close()


def test_detect_search_backend_prefers_icu_for_thai(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "plain.db"
    _make_db(db)
    with _open_test_db(db) as conn:
        monkeypatch.setattr(
            "thera.corpus._fts_table_kinds",
            lambda _conn: {"thai_royal": "fts4-icu"},
        )
        assert detect_search_backend(conn, "royal", "อนิจจัง").kind == "fts4-icu"
