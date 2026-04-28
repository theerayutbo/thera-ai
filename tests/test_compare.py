from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import thera.cli as cli

DB_PATH = Path("external/dtipitaka.db")
runner = CliRunner()


def _row(table: str, volume: int, page: int) -> sqlite3.Row:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"SELECT volume, page, items, content FROM {table} WHERE volume = ? AND page = ?",
            (volume, page),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


def _expected_text(citation: str, row: sqlite3.Row) -> str:
    body = f"{citation}\n"
    if row["items"]:
        body += f"{row['items']}\n\n"
    body += row["content"]
    if not row["content"].endswith("\n"):
        body += "\n"
    return body


def test_compare_royal_mcu_43_1_shows_both_citations() -> None:
    result = runner.invoke(
        cli.app,
        ["compare", "43:1", "43:1:mcu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[ฉบับหลวง เล่ม 43 หน้า 1]" in result.output
    assert "[มจร. เล่ม 43 หน้า 1]" in result.output
    assert "ปัฏฐาน" in result.output


def test_compare_royal_mbu_43_1_to_88_1_mbu_includes_alignment_note() -> None:
    result = runner.invoke(
        cli.app,
        ["compare", "43:1", "88:1:mbu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "royal_alignment_note: 43" in result.output
    assert "[ฉบับหลวง เล่ม 43 หน้า 1]" in result.output
    assert "[มมร. เล่ม 88 หน้า 1]" in result.output


def test_compare_royal_pali_1_1_happy_path() -> None:
    result = runner.invoke(
        cli.app,
        ["compare", "1:1", "1:1:pali"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" in result.output
    assert "[พระบาลีสยามรัฐ เล่ม 1 หน้า 1]" in result.output


def test_compare_accepts_thai_numerals_in_refs() -> None:
    arabic = runner.invoke(
        cli.app,
        ["compare", "43:1", "43:1:mcu"],
        catch_exceptions=False,
    )
    thai = runner.invoke(
        cli.app,
        ["compare", "๔๓:๑", "๔๓:๑:mcu"],
        catch_exceptions=False,
    )

    assert thai.exit_code == 0
    assert thai.output == arabic.output


def test_compare_royal_mbu_mismatch_detector_exits_65() -> None:
    result = runner.invoke(
        cli.app,
        ["compare", "43:1", "43:1:mbu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 65
    assert (
        "MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 "
        "(Patthana 4); did you mean `88:1:mbu`?"
    ) in result.stderr


def test_compare_json_outputs_two_objects_with_shared_comparison_id() -> None:
    result = runner.invoke(
        cli.app,
        ["compare", "43:1", "88:1:mbu", "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payloads = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert len(payloads) == 2
    assert payloads[0]["comparison_id"] == payloads[1]["comparison_id"]
    assert payloads[0]["royal_alignment_note"] == 43
    assert payloads[1]["royal_alignment_note"] == 43
    assert payloads[1]["citation"]["edition"] == "mbu"
    assert payloads[1]["citation"]["volume"] == 88


@pytest.mark.parametrize("bad_ref", ["43", "43:", "43:1:fake"])
def test_compare_malformed_refs_exit_64(bad_ref: str) -> None:
    result = runner.invoke(
        cli.app,
        ["compare", bad_ref, "43:1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64


def test_compare_subprocess_output_matches_sql_for_both_blocks() -> None:
    royal = _row("thai_royal", 43, 1)
    mbu = _row("thai_mbu", 88, 1)
    expected = (
        "royal_alignment_note: 43\n"
        "--- A ---\n"
        f"{_expected_text('[ฉบับหลวง เล่ม 43 หน้า 1]', royal)}"
        "--- B ---\n"
        f"{_expected_text('[มมร. เล่ม 88 หน้า 1]', mbu)}"
    )
    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}

    result = subprocess.run(
        [sys.executable, "-m", "thera.cli", "compare", "43:1", "88:1:mbu"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == expected
