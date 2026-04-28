> 🌏 [Read in English](ARCHITECTURE.md)

# Thera AI Architecture

Thera เป็น local retrieval-only CLI invariant หลักคือข้อความ canonical ที่พิมพ์ออก
stdout ต้องมาจาก SQLite corpus row เท่านั้น ไม่ใช่ model, summary, หรือ normalization pass

## Module Map

modules ปัจจุบันใน `src/thera/`:

| Module | Responsibility |
|---|---|
| `cli.py` | Typer application, command parsing, output rendering, exit-code mapping |
| `corpus.py` | read-only SQLite access, search backend selection, MBU mapping helpers |
| `corpus_setup.py` | D-Tipitaka download/checksum/import และ corpus validation |
| `citation.py` | edition keys, citation rendering, Thai/Arabic numeral parsing |
| `sikkhapada.py` | Mahavibhanga/Bhikkhuni-vibhanga สิกขาบท parser และ honest parse report |
| `__init__.py` | package version surface |

modules เหล่านี้ไม่มี LLM call คำสั่ง retrieval เปิด `external/dtipitaka.db`
ผ่าน `corpus.open_db()` ซึ่งใช้ read-only SQLite URI พร้อม `mode=ro`

## Command Surfaces

`cli.py` expose:

- `thera read`
- `thera search`
- `thera compare`
- `thera cross-ref`
- `thera verify`
- `thera sikkhapada`
- `thera list volumes`
- `thera corpus info|init|validate`

CLI ใช้ constants จาก spec §11:

- `EX_USAGE = 64`
- `EX_DATAERR = 65`
- `EX_SOFTWARE = 70`

Click/Typer default parser errors ถูก remap เป็น 64 เพื่อให้ behavior ใน test
และ real CLI ตรงกัน

## Corpus Layout

D-Tipitaka database มี 4 source tables:

| Edition | Table | Volumes |
|---|---|---|
| Royal Thai | `thai_royal` | 45 |
| MCU Thai | `thai_mcu` | 45 |
| MBU Thai | `thai_mbu` | 91 |
| Pali Siam | `pali_siam` | 45 |

`corpus_setup.py` pin commit `645aa33` และ validate row total ปัจจุบัน:
`129_147`

## Citation Invariants

Citation format มาจาก `citation.Citation.format()`:

```text
[ฉบับหลวง เล่ม 19 หน้า 257]
[มจร. เล่ม 19 หน้า 309]
[มมร. เล่ม 30 หน้า 412]
[พระบาลีสยามรัฐ เล่ม 19 หน้า 246]
```

output citation ใช้เลข Arabic ส่วน input parser รับทั้งเลข Arabic และเลขไทยผ่าน
`parse_volume_arg()` และ `parse_page_arg()`

รูปแบบที่ห้าม:

- ไม่มี citation ที่ไม่บอก edition
- ไม่มี citation ที่ผสมหลาย edition ใน text block เดียว
- ไม่มีการ rewrite เลขเล่ม มมร. ใน citation ถ้า DB row คือ มมร. เล่ม 88
  citation ต้องเป็น `มมร. เล่ม 88`

## Verbatim Contract

กฎ rendering ที่เสี่ยงที่สุดคือ: อย่าให้ formatting library แก้ source content
สำหรับ passage body เต็ม `cli.py` ใช้ `sys.stdout.write()` ผ่าน helper เช่น
`_format_passage_text()` และ `_print_passage_text()` เพื่อรักษา leading tabs,
source newlines, และ spacing จากต้นฉบับ

search snippets เป็นข้อยกเว้นเฉพาะในแง่ที่ snippet คือ excerpt สำหรับ render เท่านั้น
source `content` field ไม่ถูกแก้ และ JSON output มี raw content พร้อม match offsets

tests บังคับ byte-equal behavior โดยเทียบ subprocess CLI stdout กับ direct SQL จาก
`external/dtipitaka.db`

## MBU Mapping Invariants

ฉบับ มมร. มี 91 เล่ม และไม่ align แบบ 1:1 กับฉบับหลวง `corpus.py` จึงกำหนด:

- `ROYAL_TO_MBU`
- `MBU_TO_ROYAL`
- `to_mbu_volumes(royal_volume)`
- `from_mbu_volume(mbu_volume)`

invariant จาก spec §3 และ LOKI R3:

- MBU volume 1..91 ทุกเล่ม map ไป Royal volume เดียวเท่านั้น
- ไม่มี MBU volume ซ้ำใน Royal list มากกว่าหนึ่งรายการ
- `len(MBU_TO_ROYAL) == 91`
- `len({m for ms in ROYAL_TO_MBU.values() for m in ms}) == 91`

ผลต่อคำสั่ง:

- `read --edition mbu` ถือ volume argument เป็น Royal แล้ว map
- `read --edition mbu --raw-mbu-vol N` ถือ `N` เป็น MBU volume ตรงๆ
- `compare V:P:mbu` ถือ `V` เป็น MBU volume ตามตัวอักษร
- `cross-ref` fold MBU hits ใต้ Royal-equivalent groups

## สิกขาบท Reading A

`sikkhapada.py` implement v1.0 Reading A lock จาก DESIGN_LOG §26:

- bhikkhu: parse จากฉบับหลวง เล่ม 1-2
- bhikkhuni: parse จากฉบับหลวง เล่ม 3 เท่านั้น
- ถ้า parsed count ไม่ครบ ให้ emit exit 70 diagnostic และ abstain

นี่เป็น deliberate behavior คำสั่งต้องไม่เติม bhikkhuni shared สิกขาบท จาก inference
Reading B ต้องมี canonical mapping artifact ในอนาคตก่อน

## Test Conventions

decision history อยู่ใน `DESIGN_LOG.md`; tests ทำตาม locks เหล่านี้:

- §19.1: DEV ไม่เขียน LOKI verdicts ข้อความ handoff ใช้ template
  "awaiting LOKI verify-and-sign"
- §19.2: command flags ทุกตัวต้องมี CliRunner parser coverage ด้วย
  `runner.invoke(cli.app, [...], catch_exceptions=False)`
- §19.3: command ที่แตะ corpus หรือ network ต้องมี real-corpus หรือ real-network
  integration test ผ่าน `subprocess.run`

conventions เพิ่มเติม:

- mock fixtures ควรมี real-world bytes/data shapes เท่าที่ทำได้ `verify` tests
  รวม cp874 byte shape ที่เคยทำให้ strict TIS-620 decoding พัง
- network tests mark ด้วย `@pytest.mark.verify` และ skip by default
- corpus init tests ใช้ pinned checksum payloads; real-corpus validate tests
  รันกับ `external/dtipitaka.db`

## Decision Sources

ใช้ไฟล์เหล่านี้ตามลำดับ:

1. `DESIGN_LOG.md` สำหรับ durable architecture decisions และ LOKI verdicts
2. `docs/CLI_SPEC.md` สำหรับ Phase 4 command contract
3. `HANDOFF.md` สำหรับ current task state
4. `SESSION_LOG.md` สำหรับ implementation evidence

spec amendments ต้องผ่าน ARIA ส่วน verification verdicts ต้องผ่าน LOKI
DEV implement และ record evidence โดยไม่ claim review outcome

## File-State Rules

`external/` คือ acquisition/corpus state ไม่ใช่ source สำหรับ public repo ห้าม commit:

- `external/dtipitaka.db`
- `*.db`, `*.db-shm`, `*.db-wal`, `*.db-journal`
- `data/`
- `.aria/`, `.ai-memory/`, local handoff/session/design logs
- credentials หรือ `.env` files

public repository ควรมี source, tests, docs, packaging metadata, และ MIT license
ผู้ใช้สร้าง corpus เองด้วย `thera corpus init`
