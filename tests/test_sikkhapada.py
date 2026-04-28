"""§9 + §19.2 — `thera sikkhapada` CLI parser tests.

All flag-bearing cases use `CliRunner.invoke(cli.app, [...])` per §19.2 so
typer/click parser errors surface as test failures. Includes a subprocess
byte-equal proof against direct SQL per §12.1 verbatim contract.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

import thera.cli as cli
from thera.sikkhapada import parse_sikkhapada

DB_PATH = Path("external/dtipitaka.db")
runner = CliRunner()


def _open_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row(table: str, volume: int, page: int) -> sqlite3.Row:
    conn = _open_ro()
    try:
        row = conn.execute(
            f"SELECT volume, page, items, content FROM {table} "
            "WHERE volume = ? AND page = ?",
            (volume, page),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


def test_bhikkhu_default_exits_70_with_diagnostic_when_count_mismatches() -> None:
    """§9.3 hard-count enforcement + §1.4 abstain>guess: parser must NOT pad."""
    result = runner.invoke(cli.app, ["sikkhapada", "bhikkhu"], catch_exceptions=False)

    assert result.exit_code == 70, (
        f"expected exit 70 for hard-count mismatch, got {result.exit_code}; "
        f"stderr={result.stderr!r}"
    )
    assert "expected 227" in result.stderr
    assert "abstaining per §1.4" in result.stderr
    assert "missing rule numbers" in result.stderr
    # No verbatim list emitted on stdout when abstaining (no padding).
    assert result.stdout == ""


def test_bhikkhuni_default_exits_70_with_diagnostic_when_count_mismatches() -> None:
    result = runner.invoke(cli.app, ["sikkhapada", "bhikkhuni"], catch_exceptions=False)

    assert result.exit_code == 70
    assert "expected 311" in result.stderr
    assert "abstaining per §1.4" in result.stderr
    assert result.stdout == ""


def test_bhikkhu_default_json_exits_70_with_json_diagnostic() -> None:
    result = runner.invoke(
        cli.app,
        ["sikkhapada", "bhikkhu", "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 70
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["who"] == "bhikkhu"
    assert payload["parsed_count"] < payload["expected_count"]
    assert payload["expected_count"] == 227
    assert payload["delta"] == payload["expected_count"] - payload["parsed_count"]
    assert isinstance(payload["missing"], list)
    assert len(payload["missing"]) <= 30
    assert isinstance(payload["ambiguous_notes"], list)


def test_bhikkhu_rule_1_returns_parajika_1_verbatim_with_royal_citation() -> None:
    """§9.3 acceptance #3 — single-rule lookup returns full verbatim row."""
    result = runner.invoke(
        cli.app, ["sikkhapada", "bhikkhu", "--rule", "1"], catch_exceptions=False
    )

    assert result.exit_code == 0, f"stderr={result.stderr!r}"
    # Citation line first per §2.1; format `[ฉบับหลวง เล่ม V หน้า P]`.
    first_line = result.stdout.splitlines()[0]
    assert first_line.startswith("[ฉบับหลวง เล่ม 1 หน้า ")
    # The body should reference the Parajika 1 heading material that lives on
    # the rule's anchor page.
    assert "ปาราชิก" in result.stdout


def test_bhikkhu_rule_1_subprocess_matches_sql_byte_for_byte() -> None:
    """§19.2 + verbatim proof — CLI binary output equals direct SQL row."""
    # Resolve the parser's anchor page for rule 1 first.
    conn = _open_ro()
    try:
        report = parse_sikkhapada(conn, "bhikkhu")
    finally:
        conn.close()
    rule_one = next(r for r in report.rules if r.rule_number == 1)

    row = _row("thai_royal", rule_one.vol, rule_one.page)
    citation = f"[ฉบับหลวง เล่ม {rule_one.vol} หน้า {rule_one.page}]"
    expected = f"{citation}\n"
    if row["items"]:
        expected += f"{row['items']}\n\n"
    expected += row["content"]
    if not row["content"].endswith("\n"):
        expected += "\n"

    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}
    result = subprocess.run(
        [sys.executable, "-m", "thera.cli", "sikkhapada", "bhikkhu", "--rule", "1"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout == expected


def test_bhikkhu_rule_json_payload_is_well_formed() -> None:
    result = runner.invoke(
        cli.app,
        ["sikkhapada", "bhikkhu", "--rule", "1", "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["who"] == "bhikkhu"
    assert payload["rule_number"] == 1
    assert payload["citation"]["edition"] == "royal"
    assert payload["citation"]["pitaka"] == "vinaya"
    assert "content" in payload  # full verbatim content string
    assert payload["content"]  # non-empty


def test_unknown_who_exits_64() -> None:
    result = runner.invoke(
        cli.app, ["sikkhapada", "monk"], catch_exceptions=False
    )

    assert result.exit_code == 64
    assert "Unknown sikkhapada target" in result.stderr


def test_unknown_format_exits_64() -> None:
    result = runner.invoke(
        cli.app,
        ["sikkhapada", "bhikkhu", "--format", "yaml"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64


def test_invalid_rule_arg_exits_64() -> None:
    result = runner.invoke(
        cli.app,
        ["sikkhapada", "bhikkhu", "--rule", "abc"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64
    assert "Invalid --rule" in result.stderr


def test_rule_not_found_in_parsed_set_exits_1() -> None:
    """`--rule N` for an unparsed rule number falls into the not-found path."""
    result = runner.invoke(
        cli.app,
        ["sikkhapada", "bhikkhu", "--rule", "999"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "rule 999 not located" in result.stderr


def test_rule_accepts_thai_numeral_arg() -> None:
    """§2.5 input-side numeral parsing applies to --rule too."""
    arabic = runner.invoke(
        cli.app, ["sikkhapada", "bhikkhu", "--rule", "1"], catch_exceptions=False
    )
    thai = runner.invoke(
        cli.app, ["sikkhapada", "bhikkhu", "--rule", "๑"], catch_exceptions=False
    )

    assert thai.exit_code == 0
    assert thai.stdout == arabic.stdout


def test_parser_never_pads_or_truncates_to_target_count() -> None:
    """§1.4 abstain>guess invariant — parsed_count equals what the patterns
    actually located, with no synthetic entries inserted to reach 227/311."""
    conn = _open_ro()
    try:
        bhikkhu = parse_sikkhapada(conn, "bhikkhu")
        bhikkhuni = parse_sikkhapada(conn, "bhikkhuni")
    finally:
        conn.close()

    assert bhikkhu.expected_count == 227
    assert bhikkhuni.expected_count == 311
    # Honest report: parsed list length matches parsed_count exactly.
    assert len(bhikkhu.rules) == bhikkhu.parsed_count
    assert len(bhikkhuni.rules) == bhikkhuni.parsed_count
    # Missing list complements parsed list — they cover 1..expected exactly.
    bhikkhu_seen = {r.rule_number for r in bhikkhu.rules}
    bhikkhu_full = set(range(1, 228))
    assert bhikkhu_seen | set(bhikkhu.missing) == bhikkhu_full
    assert bhikkhu_seen.isdisjoint(bhikkhu.missing)


def test_first_n_chars_excerpt_is_verbatim_and_marked_when_truncated() -> None:
    """§9.2 first-N-chars verbatim summary + ellipsis on truncation."""
    conn = _open_ro()
    try:
        report = parse_sikkhapada(conn, "bhikkhu")
    finally:
        conn.close()

    truncated = [r for r in report.rules if r.is_truncated]
    not_truncated = [r for r in report.rules if not r.is_truncated]

    assert truncated, "expected at least one rule body longer than the summary window"
    for rule in truncated:
        assert rule.excerpt.endswith("…")
    for rule in not_truncated:
        assert not rule.excerpt.endswith("…")

    # Verbatim contract — excerpt bytes appear verbatim in the source row,
    # modulo the newline-to-space normalization documented in _make_excerpt.
    sample = report.rules[0]
    row = _row("thai_royal", sample.vol, sample.page)
    body_window = row["content"][sample.body_offset:].lstrip(" \t\r\n")
    body_window_oneline = body_window.replace("\r\n", "\n").replace("\n", " ")
    if sample.is_truncated:
        assert sample.excerpt[:-1] == body_window_oneline[: len(sample.excerpt) - 1]
    else:
        assert sample.excerpt == body_window_oneline[: len(sample.excerpt)]
