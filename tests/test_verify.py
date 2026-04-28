from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.error import URLError

import pytest
from typer.testing import CliRunner

import thera.cli as cli

DB_PATH = Path("external/dtipitaka.db")
runner = CliRunner()


class _MockResponse:
    def __init__(self, text: str) -> None:
        self._body = b"\xa0" + text.encode("cp874")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None


def _content(volume: int, page: int, table: str = "thai_royal") -> str:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            f"SELECT content FROM {table} WHERE volume = ? AND page = ?",
            (volume, page),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row[0]


def _anchor(volume: int, page: int, table: str = "thai_royal") -> str:
    return cli._anchor_from_content(_content(volume, page, table))


def test_verify_primary_url_match_exits_0(monkeypatch) -> None:
    anchor = _anchor(1, 1)

    def fake_urlopen(request, timeout):
        assert "r.php?B=1&A=1" in request.full_url
        assert timeout == cli.FETCH_TIMEOUT_SECONDS
        return _MockResponse(f"<html>{anchor}</html>")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(cli.app, ["verify", "1", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "match" in result.output
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" in result.output


def test_verify_derived_offset_writes_cache(monkeypatch, tmp_path: Path) -> None:
    anchor = _anchor(25, 1)
    cache = tmp_path / ".84000_offsets.tsv"
    monkeypatch.setattr(cli, "OFFSET_CACHE_PATH", cache)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    def fake_urlopen(request, timeout):
        url = request.full_url
        if url.endswith("B=25&A=1"):
            return _MockResponse("<html>wrong page</html>")
        if url.endswith("B=25"):
            return _MockResponse('<a href="r.php?B=25&A=4">page</a>')
        if url.endswith("B=25&A=4"):
            return _MockResponse(f"<html>{anchor}</html>")
        return _MockResponse("<html>wrong candidate</html>")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(cli.app, ["verify", "25", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "derived offset: 3" in result.output
    line = cache.read_text(encoding="utf-8").strip()
    fields = line.split("\t")
    assert fields[0] == "25"
    assert fields[1] == "3"
    assert fields[2]


def test_verify_anchor_not_found_exits_65(monkeypatch) -> None:
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    def fake_urlopen(_request, timeout):
        return _MockResponse("<html>no anchor here</html>")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(cli.app, ["verify", "1", "1"], catch_exceptions=False)

    assert result.exit_code == 65
    assert "anchor not found in 84000 vol 1" in result.stderr


def test_verify_network_failure_exits_70_with_url(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(cli.app, ["verify", "1", "1"], catch_exceptions=False)

    assert result.exit_code == 70
    assert "https://84000.org/tipitaka/read/r.php?B=1&A=1" in result.stderr
    assert "offline" in result.stderr


def test_verify_pali_not_supported_exits_64() -> None:
    result = runner.invoke(
        cli.app,
        ["verify", "1", "1", "--edition", "pali"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64
    assert "not supported by 84000.org in v1" in result.stderr


def test_verify_mbu_not_supported_exits_64() -> None:
    result = runner.invoke(
        cli.app,
        ["verify", "1", "1", "--edition", "mbu"],
        catch_exceptions=False,
    )

    assert result.exit_code == 64
    assert "not supported by 84000.org in v1" in result.stderr


def test_verify_out_of_range_volume_exits_64() -> None:
    result = runner.invoke(cli.app, ["verify", "99", "1"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "volume 99 out of range 1..45" in result.stderr


def test_verify_json_output(monkeypatch) -> None:
    anchor = _anchor(1, 1)

    def fake_urlopen(_request, timeout):
        return _MockResponse(f"<html>{anchor}</html>")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(
        cli.app,
        ["verify", "1", "1", "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert '"verdict": "match"' in result.output
    assert '"offset": 0' in result.output


def test_verify_accepts_thai_numerals(monkeypatch) -> None:
    anchor = _anchor(1, 1)

    def fake_urlopen(_request, timeout):
        return _MockResponse(f"<html>{anchor}</html>")

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    result = runner.invoke(cli.app, ["verify", "๑", "๑"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "[ฉบับหลวง เล่ม 1 หน้า 1]" in result.output


@pytest.mark.verify
def test_verify_1_1_real_network() -> None:
    result = runner.invoke(cli.app, ["verify", "1", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "match" in result.output


@pytest.mark.verify
def test_verify_25_1_real_network_matches() -> None:
    result = runner.invoke(cli.app, ["verify", "25", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "match" in result.output
