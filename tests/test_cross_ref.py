from __future__ import annotations

from contextlib import contextmanager

from typer.testing import CliRunner

import thera.cli as cli
from thera.corpus import SearchBackend, SearchResult

runner = CliRunner()


@contextmanager
def _dummy_db():
    yield object()


def _result(volume: int, page: int, edition: str) -> SearchResult:
    return SearchResult(
        volume=volume,
        page=page,
        edition=edition,  # type: ignore[arg-type]
        items=None,
        content="keyword",
        match_start=0,
        match_end=7,
        snippet="keyword",
        snippet_match_start=0,
        snippet_match_end=7,
    )


def _patch_cross_ref_fixture(monkeypatch, hits_by_edition: dict[str, list[SearchResult]]) -> None:
    def fake_fts_search(_conn, _keyword, edition, _limit):
        return hits_by_edition.get(edition, []), SearchBackend("like", None), False

    monkeypatch.setattr(cli, "open_db", _dummy_db)
    monkeypatch.setattr(cli, "fts_search", fake_fts_search)


def test_cross_ref_groups_hits_under_royal_volumes(monkeypatch) -> None:
    _patch_cross_ref_fixture(
        monkeypatch,
        {
            "royal": [_result(19, 257, "royal")],
            "mcu": [_result(19, 309, "mcu")],
            "pali": [_result(19, 246, "pali")],
            "mbu": [_result(30, 412, "mbu")],
        },
    )

    result = runner.invoke(cli.app, ["cross-ref", "อริยสัจ"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "เล่ม 19" in result.output
    assert "Royal: 1 hits  (pages 257)" in result.output
    assert "มมร. (vol 30): 1 hits combined  (vol 30 pages 412)" in result.output


def test_cross_ref_has_no_top_level_mbu_volume_header(monkeypatch) -> None:
    _patch_cross_ref_fixture(monkeypatch, {"mbu": [_result(88, 1, "mbu")]})

    result = runner.invoke(cli.app, ["cross-ref", "ปัฏฐาน"], catch_exceptions=False)

    assert result.exit_code == 0
    assert not any(line.startswith("มมร. เล่ม ") for line in result.output.splitlines())
    assert "เล่ม 43" in result.output


def test_cross_ref_mbu_only_group_still_prints_royal_zero_hits(monkeypatch) -> None:
    _patch_cross_ref_fixture(monkeypatch, {"mbu": [_result(30, 412, "mbu")]})

    result = runner.invoke(cli.app, ["cross-ref", "mbu-only"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "เล่ม 19" in result.output
    assert "Royal: 0 hits" in result.output
    assert "มมร. (vol 30): 1 hits combined  (vol 30 pages 412)" in result.output


def test_cross_ref_multi_mbu_folding_combines_count_and_page_breakdown(monkeypatch) -> None:
    _patch_cross_ref_fixture(
        monkeypatch,
        {"mbu": [_result(30, 412, "mbu"), _result(30, 419, "mbu"), _result(31, 5, "mbu")]},
    )

    result = runner.invoke(cli.app, ["cross-ref", "อริยสัจ"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "เล่ม 19" in result.output
    assert "มมร. (vol 30+31): 3 hits combined" in result.output
    assert "vol 30 pages 412, 419; vol 31 pages 5" in result.output


def test_cross_ref_limit_caps_royal_volume_groups(monkeypatch) -> None:
    _patch_cross_ref_fixture(
        monkeypatch,
        {
            "royal": [
                _result(4, 16, "royal"),
                _result(5, 75, "royal"),
                _result(19, 257, "royal"),
            ]
        },
    )

    result = runner.invoke(
        cli.app,
        ["cross-ref", "อริยสัจ", "--limit", "2"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    headers = [line for line in result.output.splitlines() if line.startswith("เล่ม ")]
    assert headers == ["เล่ม 4", "เล่ม 5"]


def test_cross_ref_json_lines(monkeypatch) -> None:
    _patch_cross_ref_fixture(monkeypatch, {"mbu": [_result(30, 412, "mbu")]})

    result = runner.invoke(
        cli.app,
        ["cross-ref", "อริยสัจ", "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert '"royal_volume": 19' in result.output
    assert '"30": [412]' in result.output


def test_cross_ref_empty_query_exits_64() -> None:
    result = runner.invoke(cli.app, ["cross-ref", ""], catch_exceptions=False)

    assert result.exit_code == 64
    assert "empty keyword rejected" in result.stderr


def test_cross_ref_limit_zero_exits_64() -> None:
    result = runner.invoke(cli.app, ["cross-ref", "อริยสัจ", "--limit", "0"], catch_exceptions=False)

    assert result.exit_code == 64
    assert "limit must be >= 1" in result.stderr
