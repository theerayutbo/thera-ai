from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

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


def test_read_royal_1_1_matches_sql_byte_for_byte() -> None:
    row = _row("thai_royal", 1, 1)

    result = runner.invoke(cli.app, ["read", "1", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert result.output == _expected_text("[ฉบับหลวง เล่ม 1 หน้า 1]", row)


def test_read_royal_1_1_subprocess_matches_sql_byte_for_byte() -> None:
    row = _row("thai_royal", 1, 1)
    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}

    result = subprocess.run(
        [sys.executable, "-m", "thera.cli", "read", "1", "1"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == _expected_text("[ฉบับหลวง เล่ม 1 หน้า 1]", row)


def test_read_mcu_43_1_returns_patthana_content() -> None:
    row = _row("thai_mcu", 43, 1)

    result = runner.invoke(
        cli.app,
        ["read", "43", "1", "--edition", "mcu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert result.output == _expected_text("[มจร. เล่ม 43 หน้า 1]", row)
    assert "ปัฏฐาน" in result.output


def test_read_mbu_43_1_maps_to_mbu_88() -> None:
    row = _row("thai_mbu", 88, 1)

    result = runner.invoke(
        cli.app,
        ["read", "43", "1", "--edition", "mbu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert result.output == _expected_text("[มมร. เล่ม 88 หน้า 1]", row)


def test_read_mbu_25_1_requires_multi_volume_disambiguation() -> None:
    result = runner.invoke(
        cli.app,
        ["read", "25", "1", "--edition", "mbu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 65
    assert "Royal vol 25 spans 9 MBU vols" in result.output
    assert "[มมร. เล่ม 39] pages 1-" in result.output
    assert "[มมร. เล่ม 47] pages 1-" in result.output
    assert "--raw-mbu-vol 39" in result.output


def test_read_mbu_raw_mbu_vol_bypasses_mapping() -> None:
    row = _row("thai_mbu", 39, 1)

    result = runner.invoke(
        cli.app,
        ["read", "25", "1", "--edition", "mbu", "--raw-mbu-vol", "39"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert result.output == _expected_text("[มมร. เล่ม 39 หน้า 1]", row)


def test_read_out_of_range_volume_exits_64() -> None:
    result = runner.invoke(cli.app, ["read", "99", "1"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "volume 99 out of range 1..45" in result.stderr


def test_read_missing_page_exits_1() -> None:
    result = runner.invoke(cli.app, ["read", "1", "9999"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "no passage at (1, 9999, royal)" in result.stderr


def test_read_accepts_thai_numeral_volume_and_page() -> None:
    arabic = runner.invoke(cli.app, ["read", "43", "1"], catch_exceptions=False)
    thai = runner.invoke(cli.app, ["read", "๔๓", "๑"], catch_exceptions=False)

    assert thai.exit_code == 0
    assert thai.output == arabic.output


def test_read_unknown_edition_exits_64() -> None:
    result = runner.invoke(
        cli.app,
        ["read", "1", "1", "--edition", "unknown_edition"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64
