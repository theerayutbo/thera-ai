> 🌏 [Read in English](QUICKSTART.md)

# Thera AI Quickstart

เอกสารนี้พาจาก fresh checkout ไปถึงการค้น/อ่านพระไตรปิฎกด้วย CLI ภายในไม่กี่นาที
เมื่อมี `external/dtipitaka.db` แล้ว Thera จะเป็น offline-first tool

## Prerequisites

- Python 3.11 หรือใหม่กว่า
- disk ประมาณ 600 MB สำหรับ `external/dtipitaka.db`
- network สำหรับ `corpus init` ครั้งแรก และสำหรับ `verify`
- หลังมี corpus แล้ว `read`, `search`, `compare`, `cross-ref`, และ `sikkhapada`
  ไม่ต้องใช้ network

ติดตั้งจาก local clone:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
thera --help
```

development shortcut โดยไม่ติดตั้ง:

```bash
PYTHONPATH=src python -m thera.cli --help
```

## Corpus Setup

ดาวน์โหลดและ checksum-verify D-Tipitaka corpus ที่ pin ไว้:

```bash
thera corpus init
```

ถ้ามี `external/dtipitaka.db` อยู่แล้ว Thera จะไม่ overwrite:

```text
corpus init failed: corpus already exists at external/dtipitaka.db; pass --force to overwrite
```

ตรวจฐานข้อมูล:

```bash
thera corpus validate
```

รูปทรง v1.0 corpus:

```text
pali_siam: 21915 rows, 0 NULL content
thai_mbu: 62380 rows, 0 NULL content
thai_mcu: 25155 rows, 0 NULL content
thai_royal: 19697 rows, 0 NULL content
total: 129147 rows (expected 129147, ±1% tolerance)
validate OK
```

## Session 1: อ่านหน้าหนึ่งจากฉบับหลวง

```bash
thera read 1 1
```

ผลลัพธ์ขึ้นต้น:

```text
[ฉบับหลวง เล่ม 1 หน้า 1]
1

                    พระวินัยปิฎก
                        เล่ม ๑
                มหาวิภังค์ ปฐมภาค
```

ข้อความนี้มาจาก SQL:

```sql
SELECT items, content FROM thai_royal WHERE volume = 1 AND page = 1;
```

เลขไทยใช้เป็น input ได้:

```bash
thera read ๔๓ ๑
```

## Session 2: ค้นหัวข้อ

```bash
thera search "อริยสัจ" --limit 2
```

ถ้า SQLite ICU FTS ยังไม่โหลด ระบบจะ fallback เป็น linear scan:

```text
[fallback: linear scan, slow]
[ฉบับหลวง เล่ม 4 หน้า 16]
items: 14
...
[truncated at 2 — use --limit to expand]
```

ค้นทั้ง 4 ฉบับ:

```bash
thera search "อริยสัจ" --edition all --limit 1
```

## Session 3: เทียบสองฉบับ

เทียบฉบับหลวง เล่ม 43 หน้า 1 กับ มมร. เล่มที่ align แล้ว:

```bash
thera compare 43:1 88:1:mbu
```

คำสั่งแสดง Royal cluster เดียวกัน และแยก citation ของแต่ละฉบับ:

```text
royal_alignment_note: 43
--- A ---
[ฉบับหลวง เล่ม 43 หน้า 1]
...
--- B ---
[มมร. เล่ม 88 หน้า 1]
...
```

ข้อผิดพลาดที่พบบ่อยคือพิมพ์ มมร. เล่ม 43 เพื่อเทียบกับฉบับหลวง เล่ม 43:

```bash
thera compare 43:1 43:1:mbu
```

Thera จะออกด้วย exit 65:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

## Session 4: Cross-Reference หัวข้อ

```bash
thera cross-ref "อริยสัจ" --limit 1
```

ผลลัพธ์จริงจาก corpus ปัจจุบันขึ้นต้น:

```text
[fallback: linear scan, slow]
เล่ม 1
  Royal: 0 hits
  มมร. (vol 1+3): 4 hits combined  (vol 1 pages 186, 205, 211; vol 3 pages 478)
```

จุดสำคัญคือ grouping: hit จาก มมร. ถูก fold ใต้ Royal-equivalent volume
ไม่ใช้เลขเล่ม มมร. เป็น top-level group

## Session 5: Lookup สิกขาบท

ดึง bhikkhu สิกขาบท เฉพาะข้อ:

```bash
thera sikkhapada bhikkhu --rule 1
```

ผลลัพธ์ขึ้นต้น:

```text
[ฉบับหลวง เล่ม 1 หน้า 14]
10

                ปาราชิกกัณฑ์ ปฐมปาราชิกสิกขาบท
                        เรื่องพระสุทินน์
```

list mode เข้มงวด ถ้า parser หาได้ไม่ครบตามจำนวนที่คาดไว้ จะ exit 70 แทนการเติมเอง:

```bash
thera sikkhapada bhikkhuni
```

diagnostic ของ v1.0 Reading A:

```text
sikkhapada parser yielded 139 bhikkhuni rules, expected 311.
delta: 172 rule(s); abstaining per §1.4 — never pad or truncate.
```

## Session 6: Verify กับ 84000.org

เมื่อมี network:

```bash
thera verify 1 1
```

คำสั่งนี้เทียบข้อความฉบับหลวงกับ 84000.org โดย decode แบบ cp874/TIS-620
ถ้า DNS หรือ outbound network ถูกบล็อก คำสั่งจะ exit 70:

```text
network failure while fetching https://84000.org/tipitaka/read/r.php?B=1&A=1: ...
```

คำสั่ง offline ยังใช้ได้ตามปกติ

## Common Workflows

อ่านข้ามฉบับ:

```bash
thera read 43 1
thera read 43 1 --edition mcu
thera read 43 1 --edition mbu
```

ฉบับหลวง เล่ม 43 map ไป มมร. เล่ม 88 ได้ตรง จึงอ่าน page 1 ได้ทันที
แต่ฉบับหลวง เล่ม 25 map ไป มมร. 9 เล่ม จึงต้องระบุ raw MBU volume:

```bash
thera read 25 1 --edition mbu
thera read 25 1 --edition mbu --raw-mbu-vol 39
```

copy citation ที่มีเลขไทย:

```bash
thera read ๔๓ ๑
thera compare ๔๓:๑ ๘๘:๑:mbu
```

## Troubleshooting

### FTS Missing

อาการ:

```text
[fallback: linear scan, slow]
```

นี่ไม่ใช่ failure แปลว่า SQLite ICU FTS ไม่พร้อมใช้งาน Thera จึงใช้ `LIKE`
กับ local corpus ผลลัพธ์ยังเป็น verbatim แต่อาจช้ากว่า

### Network Blocked

อาการ:

```text
network failure while fetching https://84000.org/...
```

มีแค่ `thera verify` ที่ต้องใช้ network คำสั่ง offline ยังใช้ได้:

```bash
thera read 1 1
thera search "อริยสัจ"
thera compare 43:1 88:1:mbu
```

### MBU Mismatch

อาการ:

```text
MBU vol 43 = Dhammapada Mala-vagga, not aligned with Royal vol 43 (Patthana 4); did you mean `88:1:mbu`?
```

มมร. มี 91 เล่ม ส่วนฉบับหลวง/มจร./พระบาลีสยามรัฐมี 45 เล่ม ใช้เล่มที่ระบบแนะนำ
หรือใช้ `thera read <royal-vol> <page> --edition mbu` แล้วทำตาม disambiguation prompt
