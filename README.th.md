> 🌏 [Read in English](README.md)

# Thera AI

CLI สำหรับค้นและอ่านพระไตรปิฎกแบบ zero-hallucination: ดึงข้อความตามต้นฉบับ,
แสดง citation, และเทียบข้ามฉบับโดยไม่สังเคราะห์เนื้อหา

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: v1.0 candidate](https://img.shields.io/badge/status-v1.0_candidate-blue.svg)](DESIGN_LOG.md)
[![PyPI: later](https://img.shields.io/badge/PyPI-later-lightgrey.svg)](#quick-install)

## What Is This

Thera AI คือ CLI สำหรับอ่านพระไตรปิฎกภาษาไทยจากฐานข้อมูล D-Tipitaka SQLite
ในเครื่อง ทุกคำสั่งดึงข้อความจาก corpus โดยตรงและแสดง citation ระบุฉบับ เล่ม
และหน้าให้ชัดเจน

แนวคิดหลักคือ Buddhawajana-first: เครื่องมือมีหน้าที่ค้น อ่าน และเทียบข้อความ;
ผู้ใช้เป็นผู้ตีความ Retrieval mode ไม่มี LLM call, ไม่มี summary, ไม่แก้คำผิดใน
ต้นฉบับ และไม่ normalize ช่องว่างหรือรูปแบบในเนื้อหาพระไตรปิฎก ถ้าข้อมูลใน corpus
ไม่พอ เครื่องมือจะหยุดพร้อม diagnostic แทนการเดา

นี่ไม่ใช่ chatbot, ไม่ใช่ชั้นอรรถกถา, และไม่ใช่เครื่องมือสร้าง สิกขาบท ที่ corpus
ไม่ได้ให้ไว้ Thera ช่วยเปิดให้เห็นความต่างระหว่างฉบับหลวง, มจร., มมร., และ
พระบาลีสยามรัฐ แต่ไม่ตัดสินแทนผู้ใช้

## Quick Install

แพ็กเกจสาธารณะจะตามมาหลัง v1.0 public release ตอนนี้ติดตั้งจาก local clone:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

ตรวจ binary:

```bash
thera --help
```

v1.1 รวม source dumps ของ D-Tipitaka ที่ pin แล้วไว้ใน
`vendor/D-tipitaka/1.2/` เมื่อ clone repo ครบ `thera corpus init` จึงสร้าง
`external/dtipitaka.db` จากไฟล์ vendored ในเครื่องได้โดยไม่ต้องติดต่อ GitHub

ถ้าใช้แบบ development โดยไม่ติดตั้ง:

```bash
PYTHONPATH=src python -m thera.cli --help
```

## 5-Minute Walkthrough

ถ้ายังไม่มี `external/dtipitaka.db` ให้สร้าง corpus ก่อน:

```bash
thera corpus init
```

ตรวจฐานข้อมูลในเครื่อง:

```bash
thera corpus validate
```

รูปทรง corpus ปัจจุบันควรเป็น:

```text
pali_siam: 21915 rows, 0 NULL content
thai_mbu: 62380 rows, 0 NULL content
thai_mcu: 25155 rows, 0 NULL content
thai_royal: 19697 rows, 0 NULL content
total: 129147 rows (expected 129147, ±1% tolerance)
validate OK
```

อ่านฉบับหลวง เล่ม 1 หน้า 1:

```bash
thera read 1 1
```

ผลลัพธ์ขึ้นต้นด้วย citation และข้อความจาก row จริง:

```text
[ฉบับหลวง เล่ม 1 หน้า 1]
1

                    พระวินัยปิฎก
                        เล่ม ๑
                มหาวิภังค์ ปฐมภาค
```

ค้นในฉบับหลวง:

```bash
thera search "อริยสัจ" --limit 2
```

ถ้า SQLite ICU FTS ยังไม่ถูกโหลด Thera จะยังทำงานด้วย fallback:

```text
[fallback: linear scan, slow]
[ฉบับหลวง เล่ม 4 หน้า 16]
items: 14
...
[truncated at 2 — use --limit to expand]
```

เทียบ ปัฏฐาน ฉบับหลวงกับ มมร. เล่มที่ align แล้ว:

```bash
thera compare 43:1 88:1:mbu
```

ผลลัพธ์มี:

```text
royal_alignment_note: 43
--- A ---
[ฉบับหลวง เล่ม 43 หน้า 1]
...
--- B ---
[มมร. เล่ม 88 หน้า 1]
...
```

ตรวจเทียบกับ 84000.org เมื่อมี network:

```bash
thera verify 1 1
```

ถ้า network ถูกบล็อก `verify` จะออกด้วย exit 70 แต่คำสั่ง offline เช่น
`read`, `search`, `compare`, `cross-ref`, และ `sikkhapada` ยังใช้งานได้

## Architecture Overview

Thera ใช้ D-Tipitaka SQLite corpus ที่ commit `645aa33` ฐานข้อมูลในเครื่องมีขนาด
ประมาณ 555 MB และมี 129,147 rows ใน 4 source tables:

| Edition key | Table | Role | Volumes |
|---|---|---|---|
| `royal` | `thai_royal` | ฉบับหลวงภาษาไทยหลัก | 45 |
| `mcu` | `thai_mcu` | ฉบับ มจร. | 45 |
| `mbu` | `thai_mbu` | ฉบับ มมร. | 91 |
| `pali` | `pali_siam` | พระบาลีสยามรัฐ อักษรไทย | 45 |

ฉบับหลวงเป็น reading surface เริ่มต้น ส่วน มจร., มมร., และพระบาลีสยามรัฐใช้สำหรับ
cross-reference และ comparison ฉบับ มมร. มี 91 เล่ม จึงต้องมี mapping ระหว่าง
ฉบับหลวงกับ มมร. และมี mismatch detector สำหรับความผิดพลาดที่พบบ่อยที่สุด:
คิดว่าเล่ม 43 ของฉบับหลวงตรงกับเล่ม 43 ของ มมร.

## Citation Format

ทุก block ของข้อความ canonical ต้องมี citation ที่บอกฉบับ:

```text
[ฉบับหลวง เล่ม 19 หน้า 257]
[พระบาลีสยามรัฐ เล่ม 19 หน้า 246]
[มจร. เล่ม 19 หน้า 309]
[มมร. เล่ม 30 หน้า 412]
```

Edition keys:

| Key | Display |
|---|---|
| `royal` | `ฉบับหลวง` |
| `mcu` | `มจร.` |
| `mbu` | `มมร.` |
| `pali` | `พระบาลีสยามรัฐ` |

input รับได้ทั้งเลข Arabic และเลขไทย เช่น `thera read ๔๓ ๑`
แต่ citation output ใช้เลข Arabic เพื่อให้ copy/paste และ grep ง่าย

## Edition Philosophy

Thera วางแต่ละฉบับไว้ข้างกัน ไม่หลอมให้เป็นข้อความเดียว เมื่อฉบับต่างกัน CLI
จะแสดงความต่างพร้อม citation แยกตามฉบับ แล้วปล่อยการตีความให้ผู้ใช้

เลขเล่มของ มมร. ถูกแสดงอย่างตั้งใจ คำสั่ง `thera compare 43:1 43:1:mbu`
จะออกด้วย:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

ข้อความนี้เป็น guardrail เพื่อกัน citation drift แบบเงียบๆ

## Limitations

v1.0 ตีตามตัวอักษรและตั้งใจ conservative:

- `thera sikkhapada bhikkhuni` ใช้ Reading A จาก DESIGN_LOG §26: อ่านจาก
  ฉบับหลวง เล่ม 3 เท่านั้น corpus มี bhikkhuni สิกขาบท ที่กล่าวเต็ม 139 รายการ
  ไม่ใช่ 311 รายการ คำสั่งจึงออกด้วย exit 70 และ diagnostic 139/311 แทนการเติม
  ช่องว่างด้วย inference
- `thera sikkhapada bhikkhu` ปัจจุบัน parse ได้ 224/227 สิกขาบท และ list mode
  ออกด้วย exit 70 แทนการ padding ช่องที่หายไป
- อรรถกถา, NotebookLM curated slices, และ canonical personas อยู่นอก scope v1.0
- `verify` ต้องใช้ network ไปยัง 84000.org แต่ retrieval แบบ offline ยังใช้งานได้
- v1.1 ลด single point of failure จาก upstream kit119 สำหรับการสร้าง corpus
  เพราะมี vendored source ใน repo แต่ canonical snapshot ยังเป็น commit
  `645aa33` เหมือนเดิม
- ไม่มี long-lived cache หรือ service process; CLI แต่ละครั้งเปิด SQLite โดยตรง

## Contributing

decision history อยู่ใน `DESIGN_LOG.md` โปรเจกต์ใช้วงจร ARIA-LOKI-DEV:
ARIA เขียน product/spec decisions, DEV implement, และ LOKI verify ก่อนเดินขั้นต่อไป
พฤติกรรมใหม่ต้องรักษา verbatim contract, เพิ่ม CliRunner parser tests, และมี
real-corpus integration เมื่อคำสั่งแตะ corpus หรือ network

## Acknowledgments

- Thera AI มาพร้อมฐานข้อมูลพระไตรปิฎกที่ vendored จาก
  [kit119/D-tipitaka](https://github.com/kit119/D-tipitaka) (commit `645aa33`,
  ปี 2011) ซึ่งผู้พัฒนาอุทิศให้ใช้ต่อแบบ open-source / public-domain ตามไฟล์
  `README.TXT` ดูรายละเอียดการให้เครดิตที่ [NOTICE](NOTICE)
- `84000.org` สำหรับ live Royal/MCU comparator ที่ `thera verify` ใช้
- SQLite, ICU, Typer, Rich, pytest, Ruff, และ Python packaging ecosystem

## License

Thera AI เผยแพร่ภายใต้ MIT License ดู [LICENSE](LICENSE)
