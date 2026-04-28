# Royal ↔ MBU Volume Mapping (D-Tipitaka 2011 snapshot)

**Status**: derived 2026-04-26 from `thai_mbu.page=1` first-page headers across all 91 MBU volumes. Authoritative for v1 cross-edition retrieval. Re-verify per content-spot-check before publishing the CLI.

**Derivation**: SQL `SELECT volume, substr(content,1,140) FROM thai_mbu WHERE page=1 ORDER BY volume;` against `external/dtipitaka.db`.

## Headline Finding

| Edition | Max volume | Aligned with Royal? |
|---------|-----------|---------------------|
| `thai_royal` | 45 | ⭐ canonical |
| `pali_siam` | 45 | ✅ 1:1 |
| `thai_mcu` | 45 | ✅ 1:1 (volume number convention shared with Royal) |
| `thai_mbu` | **91** | ❌ NOT 1:1 — MBU uses finer splits |

**Implication for CLI**: Any command crossing into MBU (`thera read --edition mbu`, `thera compare <royal_ref> <mbu_ref>`, cross-edition diff in `thera search`/`thera cross-ref`) MUST translate Royal volume → MBU volume(s) via this mapping. Naïve `WHERE volume=N` against `thai_mbu` will silently return non-comparable content.

This is the systematic explanation for the per-entry "MBU vol N = unrelated content" notes that appear scattered across Wave 2/3 KM entries (e.g., abhi-vol-37, abhi-vol-40, abhi-vol-43): they are not edge cases — they are the *rule*.

## Derived mapping (Royal → MBU)

### Vinaya (Royal 1-8)

| Royal vol | Content | MBU vols |
|-----------|---------|----------|
| 1 | มหาวิภังค์ ปฐมภาค (Mahavibhanga 1) | 1, 2, 3 |
| 2 | มหาวิภังค์ ทุติยภาค (Mahavibhanga 2) | 4 |
| 3 | ภิกขุนีวิภังค์ (Bhikkhuni-vibhanga) | 5 |
| 4 | มหาวรรค ปฐมภาค (Mahavagga 1) | 6 |
| 5 | มหาวรรค ทุติยภาค (Mahavagga 2) | 7 |
| 6 | จุลวรรค ปฐมภาค (Cullavagga 1) | 8 |
| 7 | จุลวรรค ทุติยภาค (Cullavagga 2) | 9 |
| 8 | ปริวาร (Parivara) | 10 |

### Sutta (Royal 9-33)

| Royal vol | Content | MBU vols |
|-----------|---------|----------|
| 9 | ทีฆนิกาย สีลขันธวรรค (Digha-Silakkhanda) | 11, 12 |
| 10 | ทีฆนิกาย มหาวรรค (Digha-Mahavagga) | 13, 14 |
| 11 | ทีฆนิกาย ปาฏิกวรรค (Digha-Patikavagga) | 15, 16 |
| 12 | มัชฌิมนิกาย มูลปัณณาสก์ (Majjhima-Mulapannasa) | 17, 18 |
| 13 | มัชฌิมนิกาย มัชฌิมปัณณาสก์ (Majjhima-Majjhimapannasa) | 19, 20, 21 |
| 14 | มัชฌิมนิกาย อุปริปัณณาสก์ (Majjhima-Uparipannasa) | 22, 23 |
| 15 | สังยุตตนิกาย สคาถวรรค (Samyutta-Sagathavagga) | 24, 25 |
| 16 | สังยุตตนิกาย นิทานวรรค (Samyutta-Nidanavagga) | 26 |
| 17 | สังยุตตนิกาย ขันธวารวรรค (Samyutta-Khandhavagga) | 27 |
| 18 | สังยุตตนิกาย สฬายตนวรรค (Samyutta-Salayatanavagga) | 28, 29 |
| 19 | สังยุตตนิกาย มหาวารวรรค (Samyutta-Mahavagga) | 30, 31 |
| 20 | อังคุตตรนิกาย เอก-ทุก-ติกนิบาต | 32, 33, 34 |
| 21 | อังคุตตรนิกาย จตุกกนิบาต | 35 |
| 22 | อังคุตตรนิกาย ปัญจก-ฉักกนิบาต | 36 |
| 23 | อังคุตตรนิกาย สัตตก-อัฏฐก-นวกนิบาต | 37 |
| 24 | อังคุตตรนิกาย ทสก-เอกาทสกนิบาต | 38 |
| 25 | ขุททกนิกาย เล่ม ๑ (ขุททกปาฐ + ธรรมบท + อุทาน + อิติวุตตกะ + สุตตนิบาต) | 39, 40, 41, 42, 43, 44, 45, 46, 47 |
| 26 | ขุททกนิกาย เล่ม ๒ (วิมานวัตถุ + เปตวัตถุ + เถรคาถา + เถรีคาถา) | 48, 49, 50, 51, 52, 53, 54 |
| 27 | ขุททกนิกาย ชาดก ภาค ๑ | 55, 56, 57, 58, 59, 60, 61, 62 |
| 28 | ขุททกนิกาย ชาดก ภาค ๒ (มหานิบาต + เวสสันดร) | 63, 64 |
| 29 | ขุททกนิกาย มหานิทเทส | 65, 66 |
| 30 | ขุททกนิกาย จูฬนิทเทส | 67 |
| 31 | ขุททกนิกาย ปฏิสัมภิทามรรค | 68, 69 |
| 32 | ขุททกนิกาย อปทาน ภาค ๑ | 70, 71, 72 |
| 33 | ขุททกนิกาย อปทาน ภาค ๒ + พุทธวงศ์ + จริยาปิฎก | 73, 74 |

### Abhidhamma (Royal 34-45)

| Royal vol | Content | MBU vols |
|-----------|---------|----------|
| 34 | ธรรมสังคณี (Dhammasangani) | 75, 76 |
| 35 | วิภังค์ (Vibhanga) | 77, 78 |
| 36 | ธาตุกถา + ปุคคลบัญญัติ (Dhatukatha + Puggalapaññatti) | 79 |
| 37 | กถาวัตถุ (Kathavatthu) | 80, 81 |
| 38 | ยมก ภาค ๑ (Yamaka 1) | 82, 83 |
| 39 | ยมก ภาค ๒ (Yamaka 2) | 84 |
| 40 | มหาปัฏฐาน ภาค ๑ (Patthana 1) | 85 |
| 41 | มหาปัฏฐาน ภาค ๒ (Patthana 2) | 86 |
| 42 | มหาปัฏฐาน ภาค ๓ (Patthana 3 — Anuloma-Duka ปุริมํ) | 87 |
| 43 | มหาปัฏฐาน ภาค ๔ (Patthana 4 — Anuloma-Duka ปจฺฉิมํ) | 88 |
| 44 | มหาปัฏฐาน ภาค ๕ (Patthana 5 — Anuloma-Duka-Tika) | 89, 90 |
| 45 | มหาปัฏฐาน ภาค ๖ (Patthana 6 — ปัจจนีย + ปัจจนียานุโลม) | 91 |

## Reverse mapping (MBU → Royal)

For DEV implementing `thera compare <mbu_ref> <royal_ref>`:

| MBU vols | Royal vol | Pitaka |
|----------|-----------|--------|
| 1-3 | 1 | Vinaya |
| 4 | 2 | Vinaya |
| 5 | 3 | Vinaya |
| 6 | 4 | Vinaya |
| 7 | 5 | Vinaya |
| 8 | 6 | Vinaya |
| 9 | 7 | Vinaya |
| 10 | 8 | Vinaya |
| 11-12 | 9 | Sutta-Digha |
| 13-14 | 10 | Sutta-Digha |
| 15-16 | 11 | Sutta-Digha |
| 17-18 | 12 | Sutta-Majjhima |
| 19-21 | 13 | Sutta-Majjhima |
| 22-23 | 14 | Sutta-Majjhima |
| 24-25 | 15 | Sutta-Samyutta |
| 26 | 16 | Sutta-Samyutta |
| 27 | 17 | Sutta-Samyutta |
| 28-29 | 18 | Sutta-Samyutta |
| 30-31 | 19 | Sutta-Samyutta |
| 32-34 | 20 | Sutta-Anguttara |
| 35 | 21 | Sutta-Anguttara |
| 36 | 22 | Sutta-Anguttara |
| 37 | 23 | Sutta-Anguttara |
| 38 | 24 | Sutta-Anguttara |
| 39-47 | 25 | Sutta-Khuddaka-1 |
| 48-54 | 26 | Sutta-Khuddaka-2 |
| 55-62 | 27 | Sutta-Jataka-1 |
| 63-64 | 28 | Sutta-Jataka-2 |
| 65-66 | 29 | Sutta-Mahaniddesa |
| 67 | 30 | Sutta-Cullaniddesa |
| 68-69 | 31 | Sutta-Patisambhidamagga |
| 70-72 | 32 | Sutta-Apadana-1 |
| 73-74 | 33 | Sutta-Apadana-2+Buddhavamsa+Cariyapitaka |
| 75-76 | 34 | Abhi-Dhammasangani |
| 77-78 | 35 | Abhi-Vibhanga |
| 79 | 36 | Abhi-Dhatukatha+Puggalapaññatti |
| 80-81 | 37 | Abhi-Kathavatthu |
| 82-83 | 38 | Abhi-Yamaka-1 |
| 84 | 39 | Abhi-Yamaka-2 |
| 85 | 40 | Abhi-Patthana-1 |
| 86 | 41 | Abhi-Patthana-2 |
| 87 | 42 | Abhi-Patthana-3 |
| 88 | 43 | Abhi-Patthana-4 |
| 89-90 | 44 | Abhi-Patthana-5 |
| 91 | 45 | Abhi-Patthana-6 |

## Caveats / Open Questions

1. **Page-level alignment within mapped vols**: When Royal vol N maps to multiple MBU vols, page numbers do NOT continue contiguously across the MBU split. e.g., Royal vol 25 page 200 ≠ MBU vol 41 page 200. Page-level cross-edition mapping requires content lookup, not arithmetic.
2. **MBU vol 16 anomaly**: First-page header reads `๗. ลักขณสูตร / เรื่อง มหาปุริสพยากรณ์ / [๑๓๐] ข้าพเจ้า (พระอานนทเถระเจ้า) ได้สดับมาแล้ว` — appears to be a continuation of Digha-Patikavagga from vol 15 rather than a fresh volume header. Mapping correct (Royal 11), but page-1 content is mid-sutta.
3. **MBU vol 12, 19, 29, 84 anomalies**: similar — first-page headers show in-text content (sutta names, vagga starts) rather than fresh พระสุตตันตปิฎก / พระอภิธรรมปิฎก headers. Mapping inferred from neighboring volumes.
4. **MCU = 1:1 with Royal** (max vol 45) — no MCU mapping needed; treat as Royal-aligned.
5. **Pali Siam = 1:1 with Royal** (max vol 45) — no Pali mapping needed.

## Recommended use in `src/thera/corpus.py`

```python
# Derived 2026-04-26 from thai_mbu.page=1 headers across vols 1-91
# Source: docs/corpus-mbu-volume-mapping.md

ROYAL_TO_MBU: dict[int, list[int]] = {
    1: [1, 2, 3], 2: [4], 3: [5], 4: [6], 5: [7], 6: [8], 7: [9], 8: [10],
    9: [11, 12], 10: [13, 14], 11: [15, 16],
    12: [17, 18], 13: [19, 20, 21], 14: [22, 23],
    15: [24, 25], 16: [26], 17: [27], 18: [28, 29], 19: [30, 31],
    20: [32, 33, 34], 21: [35], 22: [36], 23: [37], 24: [38],
    25: list(range(39, 48)), 26: list(range(48, 55)), 27: list(range(55, 63)), 28: [63, 64],
    29: [65, 66], 30: [67], 31: [68, 69], 32: [70, 71, 72], 33: [73, 74],
    34: [75, 76], 35: [77, 78], 36: [79], 37: [80, 81], 38: [82, 83], 39: [84],
    40: [85], 41: [86], 42: [87], 43: [88], 44: [89, 90], 45: [91],
}

MBU_TO_ROYAL: dict[int, int] = {
    mbu: royal for royal, mbus in ROYAL_TO_MBU.items() for mbu in mbus
}
```

DEV must consult this mapping in any code path that joins on `volume` across editions.
