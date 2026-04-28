"""Citation formatting for Thera retrieval results.

A Thera citation is always three-part: (volume, page, edition). Page numbers are
local to each edition — they do NOT align 1:1 across editions or with 84000.org's
per-volume page anchors. Edition disclosure is therefore mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

Edition = Literal["royal", "mcu", "mbu", "pali"]

EDITION_TABLES: dict[Edition, str] = {
    "royal": "thai_royal",
    "mcu": "thai_mcu",
    "mbu": "thai_mbu",
    "pali": "pali_siam",
}

EDITION_DISPLAY: dict[Edition, str] = {
    "royal": "ฉบับหลวง",
    "mcu": "มจร.",
    "mbu": "มมร.",
    "pali": "พระบาลีสยามรัฐ",
}

PITAKA_BY_VOLUME: dict[int, Literal["vinaya", "sutta", "abhidhamma"]] = {
    **{v: "vinaya" for v in range(1, 9)},         # 1-8
    **{v: "sutta" for v in range(9, 34)},         # 9-33
    **{v: "abhidhamma" for v in range(34, 46)},   # 34-45
}

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _parse_number_arg(value: str, name: str) -> int:
    normalized = value.translate(THAI_DIGITS)
    try:
        return int(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} {value} is not a valid integer") from exc


def parse_volume_arg(value: str) -> int:
    """Parse Arabic or Thai numerals from a CLI volume argument."""
    return _parse_number_arg(value, "volume")


def parse_page_arg(value: str) -> int:
    """Parse Arabic or Thai numerals from a CLI page argument."""
    return _parse_number_arg(value, "page")


def parse_compare_ref(value: str) -> tuple[int, int, Edition]:
    """Parse compare refs shaped as V:P or V:P:edition."""
    parts = value.split(":")
    if len(parts) not in {2, 3} or not parts[0] or not parts[1]:
        raise ValueError(f"malformed ref {value!r}; expected V:P[:edition]")
    edition = parts[2] if len(parts) == 3 else "royal"
    if edition not in EDITION_TABLES:
        raise ValueError(f"unknown edition in ref {value!r}: {edition}")
    return parse_volume_arg(parts[0]), parse_page_arg(parts[1]), cast(Edition, edition)


@dataclass(frozen=True)
class Citation:
    volume: int
    page: int
    edition: Edition

    def format(self) -> str:
        """Return canonical Thai citation string."""
        return f"[{EDITION_DISPLAY[self.edition]} เล่ม {self.volume} หน้า {self.page}]"

    def pitaka(self) -> str:
        return PITAKA_BY_VOLUME[self.volume]


def format_cross_edition(volume: int, page: int, editions: list[Edition]) -> str:
    """Format a citation that references multiple editions (e.g., Royal vs MCU).

    Used when the `thera compare` command surfaces per-edition variance.
    """
    parts = [
        f"{EDITION_DISPLAY[ed]} เล่ม {volume} หน้า {page}"
        for ed in editions
    ]
    return "[" + " / ".join(parts) + "]"
