"""Thera CLI entry point.

Every command in this file is a thin wrapper around `thera.corpus` + `thera.citation`.
There is no LLM call, no synthesis, no paraphrase — only retrieval and formatting.
"""

from __future__ import annotations

import difflib
import html
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

import click
import typer
from rich.console import Console
from rich.text import Text

from thera import __version__
from thera.citation import (
    EDITION_DISPLAY,
    EDITION_TABLES,
    PITAKA_BY_VOLUME,
    Citation,
    Edition,
    parse_compare_ref,
    parse_page_arg,
    parse_volume_arg,
)
from thera.corpus import (
    DEFAULT_DB_PATH,
    MBU_TO_ROYAL,
    SearchResult,
    from_mbu_volume,
    fts_search,
    list_volumes,
    open_db,
    page_count,
    read_page,
    to_mbu_volumes,
)
from thera.corpus_setup import (
    EXPECTED_TOTAL_ROWS,
    CorpusAlreadyExistsError,
    CorpusSetupError,
    init_corpus,
    validate_corpus,
)
from thera.sikkhapada import Who as SikkhapadaWho
from thera.sikkhapada import parse_sikkhapada

app = typer.Typer(
    help="Thera — verbatim Tipitaka retrieval CLI (zero-hallucination, quote-not-paraphrase).",
    no_args_is_help=True,
    invoke_without_command=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

EX_USAGE = 64
EX_DATAERR = 65
EX_SOFTWARE = 70
VALID_SEARCH_EDITIONS = (*EDITION_TABLES.keys(), "all")
VALID_FORMATS = ("text", "json")
OFFSET_CACHE_PATH = Path("data/.84000_offsets.tsv")
FETCH_TIMEOUT_SECONDS = 20

# Spec §11 requires CLI argument errors to use EX_USAGE instead of click's
# default exit 2. BadParameter covers parser coercion failures such as
# `--limit notanint`; UsageError covers sibling bad-argument paths.
click.BadParameter.exit_code = EX_USAGE
click.UsageError.exit_code = EX_USAGE


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version is True:
        console.print(f"thera {__version__}")
        raise typer.Exit(0)


@app.command()
def read(
    volume: Annotated[str, typer.Argument(help="Volume number (1-45).")],
    page: Annotated[str, typer.Argument(help="Page number in the specified edition.")],
    edition: Annotated[str, typer.Option("--edition", "-e", help="Edition to read.")] = "royal",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
    raw_mbu_vol: Annotated[
        str | None,
        typer.Option("--raw-mbu-vol", help="Query an exact MBU volume number directly."),
    ] = None,
) -> None:
    """Print a single (volume, page) passage verbatim with citation."""
    if edition not in EDITION_TABLES:
        err_console.print(f"[red]Unknown edition:[/red] {edition}")
        raise typer.Exit(EX_USAGE)
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)
    try:
        volume_num = parse_volume_arg(volume)
        page_num = parse_page_arg(page)
        raw_mbu_num = parse_volume_arg(raw_mbu_vol) if raw_mbu_vol is not None else None
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EX_USAGE) from exc
    if page_num < 1:
        err_console.print(f"[red]page {page_num} out of range >=1[/red]")
        raise typer.Exit(EX_USAGE)
    ed = cast(Edition, edition)
    with open_db() as conn:
        if raw_mbu_num is not None:
            if ed != "mbu":
                err_console.print("[red]--raw-mbu-vol is only valid with --edition mbu[/red]")
                raise typer.Exit(EX_USAGE)
            if raw_mbu_num not in range(1, 92):
                err_console.print(f"[red]MBU volume {raw_mbu_num} not in 1..91[/red]")
                raise typer.Exit(EX_USAGE)
            passage = read_page(conn, raw_mbu_num, page_num, "mbu")
        elif ed == "mbu":
            try:
                mbu_volumes = to_mbu_volumes(volume_num)
            except ValueError as exc:
                err_console.print(f"[red]{exc}[/red]")
                raise typer.Exit(EX_USAGE) from exc
            if len(mbu_volumes) > 1:
                _print_mbu_disambiguation(conn, volume_num, page_num, mbu_volumes)
                raise typer.Exit(EX_DATAERR)
            passage = read_page(conn, mbu_volumes[0], page_num, "mbu")
        else:
            if volume_num not in range(1, 46):
                err_console.print(f"[red]volume {volume_num} out of range 1..45[/red]")
                raise typer.Exit(EX_USAGE)
            passage = read_page(conn, volume_num, page_num, ed)
    if passage is None:
        err_console.print(f"no passage at ({volume_num}, {page_num}, {edition})")
        raise typer.Exit(1)
    if output_format == "json":
        _print_read_json(passage)
    else:
        _print_read_text(passage)


def _print_read_text(passage) -> None:
    sys.stdout.write(_format_passage_text(passage))


def _format_passage_text(passage) -> str:
    text = f"{Citation(passage.volume, passage.page, passage.edition).format()}\n"
    if passage.items:
        text += f"{passage.items}\n\n"
    text += passage.content
    if not passage.content.endswith("\n"):
        text += "\n"
    return text


def _print_read_json(passage) -> None:
    payload = {
        "citation": {
            "edition": passage.edition,
            "edition_display": EDITION_DISPLAY[passage.edition],
            "volume": passage.volume,
            "page": passage.page,
            "pitaka": (
                Citation(from_mbu_volume(passage.volume), passage.page, passage.edition).pitaka()
                if passage.edition == "mbu"
                else Citation(passage.volume, passage.page, passage.edition).pitaka()
            ),
        },
        "items": passage.items,
        "content": passage.content,
    }
    print(json.dumps(payload, ensure_ascii=False))


def _print_mbu_disambiguation(conn, royal_volume: int, page: int, mbu_volumes: list[int]) -> None:
    console.print(
        f"Royal vol {royal_volume} spans {len(mbu_volumes)} MBU vols. "
        f"Specify which MBU vol holds page {page}:"
    )
    for mbu_volume in mbu_volumes:
        console.print(f"  [มมร. เล่ม {mbu_volume}] pages 1-{page_count(conn, mbu_volume, 'mbu')}")
    console.print(
        f"Use `thera read {royal_volume} {page} --edition mbu --raw-mbu-vol "
        f"{mbu_volumes[0]}` to disambiguate."
    )


@app.command(name="list")
def list_cmd(
    target: Annotated[str, typer.Argument(help="What to list: 'volumes' | 'editions'.")],
    pitaka: Annotated[
        str | None,
        typer.Option(
            "--pitaka",
            "-p",
            help="Filter volumes by pitaka: vinaya | sutta | abhidhamma.",
        ),
    ] = None,
    edition: Annotated[str, typer.Option("--edition", "-e")] = "royal",
) -> None:
    """List coverage information (volumes present, editions, etc.)."""
    if target == "editions":
        for code, table in EDITION_TABLES.items():
            console.print(f"  [cyan]{code}[/cyan]  →  table `{table}`")
        return
    if target == "volumes":
        if edition not in EDITION_TABLES:
            console.print(f"[red]Unknown edition:[/red] {edition}")
            raise typer.Exit(EX_USAGE)
        ed = cast(Edition, edition)
        with open_db() as conn:
            vols = list_volumes(conn, ed)
            for v in vols:
                pit = PITAKA_BY_VOLUME[v]
                if pitaka and pit != pitaka:
                    continue
                n = page_count(conn, v, ed)
                console.print(f"  เล่ม {v:>2}  ({pit:<11})  {n:>4} pages")
        return
    console.print(f"[red]Unknown list target:[/red] {target}")
    raise typer.Exit(EX_USAGE)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query (Thai).")],
    edition: Annotated[str, typer.Option("--edition", "-e")] = "royal",
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
) -> None:
    """Search the canon with FTS when available, otherwise LIKE fallback."""
    if not query:
        err_console.print("[red]empty query rejected[/red]")
        raise typer.Exit(EX_USAGE)
    if edition not in VALID_SEARCH_EDITIONS:
        err_console.print(f"[red]unknown edition:[/red] {edition}")
        raise typer.Exit(EX_USAGE)
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)
    if limit < 1:
        err_console.print("[red]limit must be >= 1[/red]")
        raise typer.Exit(EX_USAGE)

    editions: list[Edition] = (
        ["royal", "mcu", "mbu", "pali"] if edition == "all" else [cast(Edition, edition)]
    )

    with open_db() as conn:
        for ed in editions:
            results, backend, truncated = fts_search(conn, query, ed, limit)
            if backend.warning:
                err_console.print(Text(backend.warning))
            if output_format == "json":
                _print_search_json(results, truncated, limit)
            else:
                _print_search_text(ed, results, truncated, limit, grouped=edition == "all")


def _print_search_json(results: list[SearchResult], truncated: bool, limit: int) -> None:
    for result in results:
        payload = {
            "citation": {
                "edition": result.edition,
                "edition_display": EDITION_DISPLAY[result.edition],
                "volume": result.volume,
                "page": result.page,
                "pitaka": Citation(result.volume, result.page, result.edition).pitaka(),
            },
            "items": result.items,
            "content": result.content,
            "snippet": result.snippet,
            "match": {
                "content_start": result.match_start,
                "content_end": result.match_end,
                "snippet_start": result.snippet_match_start,
                "snippet_end": result.snippet_match_end,
            },
        }
        print(json.dumps(payload, ensure_ascii=False))
    if truncated:
        notice = {"notice": f"[truncated at {limit} — use --limit to expand]"}
        print(
            json.dumps(notice, ensure_ascii=False)
        )


def _print_search_text(
    edition: Edition,
    results: list[SearchResult],
    truncated: bool,
    limit: int,
    *,
    grouped: bool,
) -> None:
    if grouped:
        console.print(f"\n[bold]{EDITION_DISPLAY[edition]}[/bold]")
    for result in results:
        citation = Citation(result.volume, result.page, result.edition).format()
        console.print(citation)
        if result.items:
            console.print(f"items: {result.items}")
        snippet = Text(result.snippet)
        if result.snippet_match_end > result.snippet_match_start:
            snippet.stylize("bold", result.snippet_match_start, result.snippet_match_end)
        console.print(snippet)
        console.print()
    if truncated:
        console.print(Text(f"[truncated at {limit} — use --limit to expand]"))


@app.command(name="cross-ref")
def cross_ref(
    keyword: Annotated[str, typer.Argument(help="Keyword to locate across volumes and editions.")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
) -> None:
    """List keyword occurrences folded into Royal-equivalent volume groups."""
    if not keyword:
        err_console.print("[red]empty keyword rejected[/red]")
        raise typer.Exit(EX_USAGE)
    if limit < 1:
        err_console.print("[red]limit must be >= 1[/red]")
        raise typer.Exit(EX_USAGE)
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)

    with open_db() as conn:
        groups, warnings = _cross_ref_groups(conn, keyword)
    for warning in warnings:
        err_console.print(Text(warning))

    displayed = [group for group in groups if _cross_ref_group_has_hits(group)][:limit]
    if output_format == "json":
        _print_cross_ref_json(displayed)
    else:
        _print_cross_ref_text(displayed)


def _cross_ref_groups(conn, keyword: str):
    groups = [_empty_cross_ref_group(royal_volume) for royal_volume in range(1, 46)]
    warnings: list[str] = []
    for edition in ("royal", "mcu", "pali", "mbu"):
        results, backend, _ = fts_search(conn, keyword, edition, 100_000)
        if backend.warning and backend.warning not in warnings:
            warnings.append(backend.warning)
        for result in results:
            royal_volume = from_mbu_volume(result.volume) if edition == "mbu" else result.volume
            if royal_volume not in range(1, 46):
                continue
            group = groups[royal_volume - 1]
            if edition == "mbu":
                group["mbu"].setdefault(result.volume, []).append(result.page)
            else:
                group[edition].append(result.page)
    return groups, warnings


def _empty_cross_ref_group(royal_volume: int) -> dict:
    return {"royal_volume": royal_volume, "royal": [], "mcu": [], "pali": [], "mbu": {}}


def _cross_ref_group_has_hits(group: dict) -> bool:
    return bool(group["royal"] or group["mcu"] or group["pali"] or group["mbu"])


def _print_cross_ref_text(groups: list[dict]) -> None:
    for group in groups:
        sys.stdout.write(f"เล่ม {group['royal_volume']}\n")
        if group["royal"] or group["mbu"]:
            sys.stdout.write(
                f"  Royal: {len(group['royal'])} hits"
                f"{_pages_suffix(group['royal'])}\n"
            )
        if group["pali"]:
            sys.stdout.write(
                f"  {EDITION_DISPLAY['pali']}: {len(group['pali'])} hits"
                f"{_pages_suffix(group['pali'])}\n"
            )
        if group["mcu"]:
            sys.stdout.write(
                f"  {EDITION_DISPLAY['mcu']}: {len(group['mcu'])} hits"
                f"{_pages_suffix(group['mcu'])}\n"
            )
        if group["mbu"]:
            sys.stdout.write(f"  {_format_mbu_cross_ref_line(group['mbu'])}\n")
        sys.stdout.write("\n")


def _pages_suffix(pages: list[int]) -> str:
    if not pages:
        return ""
    unique_pages = sorted(set(pages))
    preview = ", ".join(str(page) for page in unique_pages[:6])
    if len(unique_pages) > 6:
        preview += ", ..."
    return f"  (pages {preview})"


def _format_mbu_cross_ref_line(mbu_hits: dict[int, list[int]]) -> str:
    mbu_volumes = sorted(mbu_hits)
    total = sum(len(pages) for pages in mbu_hits.values())
    joined_volumes = "+".join(str(volume) for volume in mbu_volumes)
    breakdown = "; ".join(
        f"vol {volume} pages {_format_page_list(mbu_hits[volume])}" for volume in mbu_volumes
    )
    return f"{EDITION_DISPLAY['mbu']} (vol {joined_volumes}): {total} hits combined  ({breakdown})"


def _format_page_list(pages: list[int]) -> str:
    unique_pages = sorted(set(pages))
    preview = ", ".join(str(page) for page in unique_pages[:6])
    if len(unique_pages) > 6:
        preview += ", ..."
    return preview


def _print_cross_ref_json(groups: list[dict]) -> None:
    for group in groups:
        payload = {
            "royal_volume": group["royal_volume"],
            "royal": {"hit_count": len(group["royal"]), "pages": sorted(set(group["royal"]))},
            "mcu": {"hit_count": len(group["mcu"]), "pages": sorted(set(group["mcu"]))},
            "pali": {"hit_count": len(group["pali"]), "pages": sorted(set(group["pali"]))},
            "mbu": {
                "hit_count": sum(len(pages) for pages in group["mbu"].values()),
                "volumes": {
                    str(volume): sorted(set(pages))
                    for volume, pages in sorted(group["mbu"].items())
                },
            },
        }
        print(json.dumps(payload, ensure_ascii=False))


@app.command()
def compare(
    ref_a: Annotated[
        str,
        typer.Argument(help="Reference 'V:P[:edition]' (e.g., 10:257 or 10:257:mcu)."),
    ],
    ref_b: Annotated[str, typer.Argument(help="Second reference, same format.")],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
) -> None:
    """Show two references side by side (for manual contradiction review)."""
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)
    try:
        parsed_a = parse_compare_ref(ref_a)
        parsed_b = parse_compare_ref(ref_b)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EX_USAGE) from exc

    mismatch = _compare_mbu_mismatch_message(parsed_a, parsed_b)
    if mismatch is not None:
        sys.stderr.write(f"{mismatch}\n")
        raise typer.Exit(EX_DATAERR)

    with open_db() as conn:
        passage_a = _read_compare_ref(conn, parsed_a)
        passage_b = _read_compare_ref(conn, parsed_b)
    if passage_a is None:
        vol, page, ed = parsed_a
        err_console.print(f"no passage at ({vol}, {page}, {ed})")
        raise typer.Exit(1)
    if passage_b is None:
        vol, page, ed = parsed_b
        err_console.print(f"no passage at ({vol}, {page}, {ed})")
        raise typer.Exit(1)

    alignment_note = _royal_alignment_note(parsed_a, parsed_b)
    if output_format == "json":
        _print_compare_json(passage_a, passage_b, alignment_note)
    else:
        _print_compare_text(passage_a, passage_b, alignment_note)


def _read_compare_ref(conn, parsed: tuple[int, int, Edition]):
    volume, page, edition = parsed
    try:
        _validate_compare_ref_range(volume, page, edition)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EX_USAGE) from exc
    return read_page(conn, volume, page, edition)


def _validate_compare_ref_range(volume: int, page: int, edition: Edition) -> None:
    if page < 1:
        raise ValueError(f"page {page} out of range >=1")
    if edition == "mbu":
        if volume not in range(1, 92):
            raise ValueError(f"MBU volume {volume} not in 1..91")
    elif volume not in range(1, 46):
        raise ValueError(f"volume {volume} out of range 1..45")


def _compare_mbu_mismatch_message(
    ref_a: tuple[int, int, Edition],
    ref_b: tuple[int, int, Edition],
) -> str | None:
    royal_ref, mbu_ref = _royal_and_mbu_refs(ref_a, ref_b)
    if royal_ref is None or mbu_ref is None:
        return None
    royal_volume, _, _ = royal_ref
    mbu_volume, mbu_page, _ = mbu_ref
    if mbu_volume not in MBU_TO_ROYAL or royal_volume not in range(1, 46):
        return None
    if MBU_TO_ROYAL[mbu_volume] == royal_volume:
        return None
    suggested = to_mbu_volumes(royal_volume)[0]
    return (
        f"MBU vol {mbu_volume} = {_volume_label('mbu', mbu_volume)}, "
        f"not aligned with Royal vol {royal_volume} ({_volume_label('royal', royal_volume)}); "
        f"did you mean `{suggested}:{mbu_page}:mbu`?"
    )


def _royal_and_mbu_refs(
    ref_a: tuple[int, int, Edition],
    ref_b: tuple[int, int, Edition],
) -> tuple[tuple[int, int, Edition] | None, tuple[int, int, Edition] | None]:
    if ref_a[2] == "royal" and ref_b[2] == "mbu":
        return ref_a, ref_b
    if ref_b[2] == "royal" and ref_a[2] == "mbu":
        return ref_b, ref_a
    return None, None


def _volume_label(edition: Edition, volume: int) -> str:
    labels = {
        ("mbu", 43): "Dhammapada Mala-vagga",
        ("royal", 43): "Patthana 4",
    }
    return labels.get((edition, volume), f"{EDITION_DISPLAY[edition]} vol {volume}")


def _royal_alignment_note(
    ref_a: tuple[int, int, Edition],
    ref_b: tuple[int, int, Edition],
) -> int | None:
    royal_a = _royal_cluster(ref_a[0], ref_a[2])
    royal_b = _royal_cluster(ref_b[0], ref_b[2])
    return royal_a if royal_a is not None and royal_a == royal_b else None


def _royal_cluster(volume: int, edition: Edition) -> int | None:
    if edition == "mbu":
        return MBU_TO_ROYAL.get(volume)
    if volume in range(1, 46):
        return volume
    return None


def _print_compare_text(passage_a, passage_b, alignment_note: int | None) -> None:
    if alignment_note is not None:
        sys.stdout.write(f"royal_alignment_note: {alignment_note}\n")
    sys.stdout.write("--- A ---\n")
    sys.stdout.write(_format_passage_text(passage_a))
    sys.stdout.write("--- B ---\n")
    sys.stdout.write(_format_passage_text(passage_b))


def _print_compare_json(passage_a, passage_b, alignment_note: int | None) -> None:
    comparison_id = (
        f"{passage_a.edition}:{passage_a.volume}:{passage_a.page}"
        f"__{passage_b.edition}:{passage_b.volume}:{passage_b.page}"
    )
    for side, passage in (("a", passage_a), ("b", passage_b)):
        payload = {
            "comparison_id": comparison_id,
            "side": side,
            "citation": {
                "edition": passage.edition,
                "edition_display": EDITION_DISPLAY[passage.edition],
                "volume": passage.volume,
                "page": passage.page,
                "pitaka": (
                    Citation(
                        from_mbu_volume(passage.volume),
                        passage.page,
                        passage.edition,
                    ).pitaka()
                    if passage.edition == "mbu"
                    else Citation(passage.volume, passage.page, passage.edition).pitaka()
                ),
            },
            "items": passage.items,
            "content": passage.content,
        }
        if alignment_note is not None:
            payload["royal_alignment_note"] = alignment_note
        print(json.dumps(payload, ensure_ascii=False))


@app.command()
def verify(
    volume: Annotated[str, typer.Argument()],
    page: Annotated[str, typer.Argument()],
    edition: Annotated[str, typer.Option("--edition", "-e")] = "royal",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
) -> None:
    """Compare D-Tipitaka passage against 84000.org live."""
    if edition not in EDITION_TABLES:
        err_console.print(f"[red]Unknown edition:[/red] {edition}")
        raise typer.Exit(EX_USAGE)
    if edition in {"pali", "mbu"}:
        err_console.print(
            f"{EDITION_DISPLAY[cast(Edition, edition)]} not supported by 84000.org in v1"
        )
        raise typer.Exit(EX_USAGE)
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)
    try:
        volume_num = parse_volume_arg(volume)
        page_num = parse_page_arg(page)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EX_USAGE) from exc
    if volume_num not in range(1, 46):
        err_console.print(f"[red]volume {volume_num} out of range 1..45[/red]")
        raise typer.Exit(EX_USAGE)
    if page_num < 1:
        err_console.print(f"[red]page {page_num} out of range >=1[/red]")
        raise typer.Exit(EX_USAGE)

    ed = cast(Edition, edition)
    with open_db() as conn:
        passage = read_page(conn, volume_num, page_num, ed)
    if passage is None:
        err_console.print(f"no passage at ({volume_num}, {page_num}, {edition})")
        raise typer.Exit(1)

    try:
        result = _verify_against_84000(passage)
    except NetworkVerifyError as exc:
        err_console.print(f"network failure while fetching {exc.url}: {exc.reason}")
        raise typer.Exit(EX_SOFTWARE) from exc

    if result["anchor_found"] is False:
        err_console.print(
            f"anchor not found in 84000 vol {volume_num} — "
            "possible content mismatch or vol-numbering divergence"
        )
        raise typer.Exit(EX_DATAERR)
    if result["offset"] != 0:
        _append_offset_cache(volume_num, result["offset"])

    if output_format == "json":
        _print_verify_json(passage, result)
    else:
        _print_verify_text(passage, result)


class NetworkVerifyError(RuntimeError):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(reason)
        self.url = url
        self.reason = reason


def _verify_against_84000(passage) -> dict:
    primary_url = _read_url_84000(passage.volume, passage.page)
    primary_html = _fetch_84000(primary_url)
    anchor = _anchor_from_content(passage.content)
    body_anchor = _body_anchor_from_content(passage.content)
    if anchor in _compact_text(primary_html):
        return {
            "anchor_found": True,
            "offset": 0,
            "url": primary_url,
            "anchor": anchor,
            "html": primary_html,
        }
    if body_anchor and body_anchor in _compact_text(primary_html):
        return {
            "anchor_found": True,
            "offset": 0,
            "url": primary_url,
            "anchor": body_anchor,
            "html": primary_html,
        }

    index_url = _index_url_84000(passage.volume)
    index_html = _fetch_84000(index_url)
    for candidate_page in _candidate_84000_pages(index_html, passage.page):
        candidate_url = _read_url_84000(passage.volume, candidate_page)
        time.sleep(1.5)
        candidate_html = _fetch_84000(candidate_url)
        candidate_text = _compact_text(candidate_html)
        if anchor in candidate_text or (body_anchor and body_anchor in candidate_text):
            return {
                "anchor_found": True,
                "offset": candidate_page - passage.page,
                "url": candidate_url,
                "anchor": anchor if anchor in candidate_text else body_anchor,
                "html": candidate_html,
            }

    return {
        "anchor_found": False,
        "offset": None,
        "url": index_url,
        "anchor": anchor,
        "html": index_html,
    }


def _read_url_84000(volume: int, page: int) -> str:
    return f"https://84000.org/tipitaka/read/r.php?B={volume}&A={page}"


def _index_url_84000(volume: int) -> str:
    return f"https://84000.org/tipitaka/read/r.php?B={volume}"


def _fetch_84000(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return response.read().decode("cp874")
    except (URLError, ConnectionError, TimeoutError, OSError, UnicodeDecodeError) as exc:
        raise NetworkVerifyError(url, str(exc)) from exc


def _anchor_from_content(content: str, length: int = 120) -> str:
    compact = _compact_text(content)
    return compact[:length]


def _body_anchor_from_content(content: str, length: int = 120) -> str:
    compact = _compact_text(content)
    item_marker = re.search(r"\[[0-9๐-๙]+\]", compact)  # noqa: RUF001
    if not item_marker:
        return ""
    return compact[item_marker.end() : item_marker.end() + length]


def _compact_text(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]*>", "", text))
    return re.sub(r"[\s.]+", "", text)


def _candidate_84000_pages(index_html: str, page: int) -> list[int]:
    linked_pages = {int(match) for match in re.findall(r"[?&]A=(\d+)", index_html)}
    nearby_pages = {candidate for candidate in range(max(1, page - 50), page + 51)}
    candidates = sorted(linked_pages | nearby_pages)
    return [candidate for candidate in candidates if candidate != page]


def _append_offset_cache(volume: int, offset: int) -> None:
    OFFSET_CACHE_PATH.parent.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with OFFSET_CACHE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{volume}\t{offset}\t{timestamp}\n")


def _print_verify_text(passage, result: dict) -> None:
    sys.stdout.write(Citation(passage.volume, passage.page, passage.edition).format())
    sys.stdout.write("\n")
    sys.stdout.write("match\n")
    sys.stdout.write(f"84000_url: {result['url']}\n")
    if result["offset"] != 0:
        sys.stdout.write(f"derived offset: {result['offset']}\n")
    diff = _verify_diff(passage.content, result["html"])
    if diff:
        sys.stdout.write(diff)


def _verify_diff(content: str, html: str) -> str:
    dtip = _compact_text(content)
    live = _compact_text(html)
    if dtip and dtip in live:
        return ""
    lines = difflib.unified_diff(
        [dtip[:300]],
        [live[:300]],
        fromfile="dtipitaka",
        tofile="84000",
        lineterm="",
    )
    diff = "\n".join(lines)
    return f"{diff}\n" if diff else ""


def _print_verify_json(passage, result: dict) -> None:
    payload = {
        "citation": {
            "edition": passage.edition,
            "edition_display": EDITION_DISPLAY[passage.edition],
            "volume": passage.volume,
            "page": passage.page,
            "pitaka": Citation(passage.volume, passage.page, passage.edition).pitaka(),
        },
        "verdict": "match",
        "offset": result["offset"],
        "url": result["url"],
        "anchor": result["anchor"],
    }
    print(json.dumps(payload, ensure_ascii=False))


@app.command()
def sikkhapada(
    who: Annotated[str, typer.Argument(help="'bhikkhu' (227 rules) | 'bhikkhuni' (311 rules).")],
    rule: Annotated[
        str | None,
        typer.Option("--rule", help="Return full verbatim text of one rule (1..N)."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json"),
    ] = "text",
) -> None:
    """List monastic training rules verbatim from Mahavibhanga / Bhikkhuni-vibhanga.

    Per spec §9: hard-count enforcement (227 / 311) — if the corpus parser cannot
    locate the expected count, exits 70 with diagnostic. Never pads or truncates
    to hit the target (§1.4 abstain>guess).
    """
    if who not in ("bhikkhu", "bhikkhuni"):
        err_console.print(
            f"[red]Unknown sikkhapada target:[/red] {who} (expected bhikkhu | bhikkhuni)"
        )
        raise typer.Exit(EX_USAGE)
    if output_format not in VALID_FORMATS:
        err_console.print(f"[red]Unknown format:[/red] {output_format}")
        raise typer.Exit(EX_USAGE)

    rule_number: int | None = None
    if rule is not None:
        try:
            rule_number = parse_volume_arg(rule)
        except ValueError as exc:
            err_console.print(f"[red]Invalid --rule value:[/red] {exc}")
            raise typer.Exit(EX_USAGE) from exc

    conn = open_db()
    try:
        report = parse_sikkhapada(conn, cast(SikkhapadaWho, who))
    finally:
        conn.close()

    if rule_number is not None:
        _emit_sikkhapada_single(who, rule_number, report, output_format)
        return

    _emit_sikkhapada_list(who, report, output_format)


def _emit_sikkhapada_list(who: str, report, output_format: str) -> None:
    """List default — exit 70 if count mismatch (§9.3 + §1.4 abstain>guess)."""
    if report.parsed_count != report.expected_count:
        _emit_sikkhapada_diagnostic(who, report, output_format)
        raise typer.Exit(EX_SOFTWARE)
    if output_format == "json":
        for rule in report.rules:
            payload = {
                "who": who,
                "rule_number": rule.rule_number,
                "citation": {
                    "edition": "royal",
                    "edition_display": EDITION_DISPLAY["royal"],
                    "volume": rule.vol,
                    "page": rule.page,
                    "pitaka": "vinaya",
                },
                "items": rule.items,
                "excerpt": rule.excerpt,
                "is_truncated": rule.is_truncated,
            }
            print(json.dumps(payload, ensure_ascii=False))
        return
    for rule in report.rules:
        citation = f"[{EDITION_DISPLAY['royal']} เล่ม {rule.vol} หน้า {rule.page}]"
        sys.stdout.write(f"{rule.rule_number:>3}. {citation} {rule.excerpt}\n")


def _emit_sikkhapada_single(
    who: str,
    rule_number: int,
    report,
    output_format: str,
) -> None:
    """`--rule N` path — load full page content for the rule's anchor row."""
    match = next((r for r in report.rules if r.rule_number == rule_number), None)
    if match is None:
        err_console.print(
            f"[red]rule {rule_number} not located by parser for {who}[/red] "
            f"(parsed {report.parsed_count}/{report.expected_count})"
        )
        raise typer.Exit(1)
    conn = open_db()
    try:
        passage = read_page(conn, match.vol, match.page, "royal")
    finally:
        conn.close()
    if passage is None:
        err_console.print(
            f"[red]citation row missing[/red]: vol={match.vol} page={match.page}"
        )
        raise typer.Exit(1)
    citation = Citation(volume=match.vol, page=match.page, edition="royal")
    if output_format == "json":
        payload = {
            "who": who,
            "rule_number": rule_number,
            "citation": {
                "edition": "royal",
                "edition_display": EDITION_DISPLAY["royal"],
                "volume": match.vol,
                "page": match.page,
                "pitaka": citation.pitaka(),
            },
            "items": passage.items,
            "content": passage.content,
            "excerpt": match.excerpt,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return
    sys.stdout.write(f"{citation.format()}\n")
    if passage.items:
        sys.stdout.write(f"{passage.items}\n\n")
    sys.stdout.write(passage.content)
    if not passage.content.endswith("\n"):
        sys.stdout.write("\n")


def _emit_sikkhapada_diagnostic(who: str, report, output_format: str = "text") -> None:
    """Diagnostic for hard-count mismatch — never pads or truncates."""
    missing = report.missing[:30]
    truncated = len(report.missing) > 30
    if output_format == "json":
        payload = {
            "who": who,
            "parsed_count": report.parsed_count,
            "expected_count": report.expected_count,
            "delta": report.expected_count - report.parsed_count,
            "missing": missing,
            "missing_truncated": truncated,
            "ambiguous_notes": report.ambiguous_notes,
        }
        err_console.print(json.dumps(payload, ensure_ascii=False))
        return
    err_console.print(
        f"[red]sikkhapada parser yielded {report.parsed_count} {who} rules, "
        f"expected {report.expected_count}.[/red]"
    )
    err_console.print(
        f"  delta: {report.expected_count - report.parsed_count} rule(s); "
        f"abstaining per §1.4 — never pad or truncate."
    )
    err_console.print(
        f"  missing rule numbers ({len(report.missing)}): "
        f"{missing}{'...' if truncated else ''}"
    )
    if report.ambiguous_notes:
        err_console.print("  ambiguous-split locations:")
        for note in report.ambiguous_notes:
            err_console.print(f"    - {note}")


@app.command()
def corpus(
    action: Annotated[str, typer.Argument(help="'init' | 'validate' | 'info'.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing corpus on init."),
    ] = False,
) -> None:
    """Manage the local corpus (D-Tipitaka SQLite)."""
    if action == "info":
        console.print(f"  DB path:   {DEFAULT_DB_PATH}")
        if DEFAULT_DB_PATH.exists():
            size_mb = DEFAULT_DB_PATH.stat().st_size / (1024 * 1024)
            console.print(f"  DB size:   {size_mb:.1f} MB")
            console.print("  DB status: [green]present[/green]")
        else:
            console.print("  DB status: [red]missing[/red] — run `thera corpus init`")
        return
    if action == "init":
        try:
            init_corpus(
                DEFAULT_DB_PATH,
                force=force,
                progress=lambda msg: err_console.print(msg),
            )
        except CorpusSetupError as exc:
            err_console.print(f"[red]corpus init failed:[/red] {exc}")
            # Existing-corpus gate should be EX_USAGE per §11; everything else
            # (network, checksum, decompress, SQL import) is EX_SOFTWARE.
            if isinstance(exc, CorpusAlreadyExistsError):
                raise typer.Exit(EX_USAGE) from exc
            raise typer.Exit(EX_SOFTWARE) from exc
        console.print(f"[green]corpus initialized at {DEFAULT_DB_PATH}[/green]")
        return
    if action == "validate":
        if not DEFAULT_DB_PATH.exists():
            err_console.print(
                f"[red]corpus DB missing at {DEFAULT_DB_PATH} — run `thera corpus init`[/red]"
            )
            raise typer.Exit(EX_USAGE)
        with open_db() as conn:
            report = validate_corpus(conn)
        for table in report.tables_present:
            console.print(
                f"  {table}: {report.row_counts[table]} rows, "
                f"{report.null_content_counts[table]} NULL content"
            )
        for table in report.tables_missing:
            console.print(f"  [red]{table}: missing[/red]")
        console.print(
            f"  total: {report.total_rows} rows "
            f"(expected {EXPECTED_TOTAL_ROWS}, ±1% tolerance)"
        )
        if report.ok:
            console.print("[green]validate OK[/green]")
            return
        for err in report.errors:
            err_console.print(f"  [red]error:[/red] {err}")
        raise typer.Exit(EX_SOFTWARE)
    console.print(f"[red]Unknown corpus action:[/red] {action}")
    raise typer.Exit(EX_USAGE)


if __name__ == "__main__":
    app()
