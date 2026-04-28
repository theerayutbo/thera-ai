# Thera AI — ใช้ทำอะไรได้จริง

> 🌏 [Read in English](USE_CASES.md)


CLI สำหรับค้นพระไตรปิฎกแบบไม่หลอก ไม่ตีความ ไม่ paraphrase

ดึงข้อความจากต้นฉบับตัวต่อตัว พร้อม citation `[ฉบับหลวง เล่ม X หน้า Y]` เปรียบเทียบ 4 ฉบับ (หลวง / มจร / มมร / พระบาลีสยามรัฐ) ได้จากคำสั่งเดียว

> **AI ในที่นี้ใช้แค่เพื่อค้น ไม่ใช่เพื่อสรุป** — ผู้ใช้ตีความเอง ไม่มี LLM แทรกระหว่างคุณกับพระวจนะ

---

## ผู้ใช้ที่ได้ประโยชน์

### 🪷 สาธุชน + ผู้ปฏิบัติธรรม

อยากอ่านพระไตรปิฎก **ตามตัวอักษร** ไม่ผ่าน AI สรุปให้ฟัง

```bash
# อยากอ่านปฏิจจสมุปบาท
thera search "ปฏิจจสมุปบาท" --limit 5

# ผลลัพธ์:
# [ฉบับหลวง เล่ม 16 หน้า 1] ...สังขารทั้งหลายมีอวิชชาเป็นปัจจัย...
# [ฉบับหลวง เล่ม 16 หน้า 50] ...
```

ได้ตัวอักษรจริง พร้อมเล่ม-หน้าเป๊ะ Copy-paste ไปใช้อ้างอิงได้เลย

### 🟠 พระภิกษุ + นักศึกษาบาลี

อยากเทียบฉบับหลวงกับ มจร เพื่อดูศัพท์ที่ต่าง

```bash
thera compare 19:528 19:528:mcu

# Output: 2 panel side-by-side
# --- A --- [ฉบับหลวง เล่ม 19 หน้า 528]
#   ...อริยสัจ ๔ คือ...
# --- B --- [มจร. เล่ม 19 หน้า 528]
#   ...อริยสัจ ๔ ได้แก่...
```

หรืออยากเช็คคำบาลี

```bash
thera read 19 528 --edition pali
# [พระบาลีสยามรัฐ เล่ม 19 หน้า 528] ...จตฺตาริ อริยสจฺจานิ...
```

### 📚 นักวิจัย + ผู้ทำงานเชิงวิชาการ

ต้องการ verbatim quote สำหรับ paper / thesis / วิจัย

```bash
# ดึงข้อความ pure-source byte-for-byte
thera read 16 1 --format json > citation.json

# JSON มี field "content" ที่ byte-equal กับ SQL row
# ใช้ paste เป็น appendix ของ paper ได้
```

อยากตรวจว่า digital edition ตรงกับ 84000.org ground-truth ไหม

```bash
thera verify 1 1
# fetch 84000 live → diff → match / show offset / "anchor not found"
```

### 🟢 นักทำ Knowledge Base พุทธศาสนา (KM curators)

ทำ KB สาย Buddhawajana ที่เน้น verbatim

```bash
# ค้นข้ามฉบับเพื่อ surface contradictions
thera cross-ref "อนิจจัง"

# Output รวมเป็นกลุ่มต่อเล่มหลวง:
# เล่ม 17 — สังยุตตนิกาย ขันธวารวรรค
#   ฉบับหลวง: 12 hits
#   มจร.: 14 hits
#   มมร. (vol 27): 13 hits
#   พระบาลีสยามรัฐ: 12 hits
```

หรือดึงสิกขาบท

```bash
# ปาราชิก 1 ของพระภิกษุ
thera sikkhapada bhikkhu --rule 1
# ได้ verbatim พร้อม [ฉบับหลวง เล่ม 1 หน้า X]

# ทั้ง 227 ข้อ — แต่ถ้าหาไม่ครบ Thera **ไม่หลอก**
thera sikkhapada bhikkhu
# parsed 224/227 → exit 70 + diagnostic บอกว่าข้อ 24, 39, 85 หายไป
# (Thera "ยอมรับว่าไม่รู้" ดีกว่าแต่งให้ครบ)
```

### 💻 Developers + Programmers

ตัวอย่าง pattern "AI ที่ไม่หลอก" สำหรับเอาไปใช้กับเอกสารศักดิ์สิทธิ์อื่นๆ (กฎหมาย / พระคัมภีร์ศาสนาอื่น / เอกสารวิทยาศาสตร์)

```bash
# ทุก output byte-equal กับ source
diff <(thera read 1 14 --format json | jq -r .content) \
     <(sqlite3 external/dtipitaka.db "SELECT content FROM thai_royal WHERE volume=1 AND page=14")
# ผลลัพธ์: empty diff (byte-identical)
```

---

## ทำไมต่างจากของอื่น

| ทางเลือก | ข้อจำกัด | Thera AI |
|---|---|---|
| ChatGPT / Claude / Gemini | paraphrase + hallucinate citation | byte-verbatim + citation จริง |
| 84000.org browser | ค้นข้ามฉบับได้แค่ Royal + MCU | รวม MBU + Pali Siam ด้วย |
| หนังสือพระไตรปิฎกเล่ม | เทียบ 4 ฉบับใช้เวลานาน | instant cross-edition diff |
| App พระไตรปิฎกอื่น | ส่วนใหญ่ closed-source / mix editions silently | open-source MIT + edition-honest |

---

## ลองใน 5 นาที

```bash
# 1. clone
git clone https://github.com/<a's-handle>/thera.git
cd thera

# 2. ติดตั้ง
pip install -e .

# 3. download corpus (~555 MB ใช้เวลาประมาณ 2-5 นาที)
thera corpus init

# 4. ทดลองคำสั่งแรก
thera search "อริยสัจ"
```

---

## คำสั่งทั้งหมด (8 คำสั่ง)

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `thera search <คำค้น>` | ค้น full-text 4 ฉบับ |
| `thera read <เล่ม> <หน้า>` | อ่านหน้าตรงๆ verbatim |
| `thera compare <ref> <ref>` | เปรียบเทียบ 2 ตำแหน่ง side-by-side |
| `thera cross-ref <คำ>` | รวมผลค้นข้ามทุกฉบับเป็นกลุ่มตามเล่มหลวง |
| `thera verify <เล่ม> <หน้า>` | เช็คตรงกับ 84000.org |
| `thera sikkhapada bhikkhu\|bhikkhuni [--rule N]` | ดูสิกขาบท |
| `thera corpus init\|validate\|info` | จัดการ corpus |

---

## คุณสมบัติทางวิศวกรรม

- ✅ **Zero LLM ในขั้น retrieval** — ไม่มี AI สรุป / แต่ง / paraphrase
- ✅ **Byte-equal verbatim** — output ตรง source ทุก byte (verified ด้วย 7 byte-equal proofs ใน test suite)
- ✅ **Edition honesty** — แสดงเล่ม-หน้าจริงของฉบับนั้น ไม่แปลง MBU vol 88 เป็น "Royal vol 43" ใน citation
- ✅ **Open source MIT** — MIT License, code review ได้ทั้งหมด
- ✅ **89/91 tests pass** — มี structural invariants ที่บังคับว่า contract zero-hallucination ต้องเป็นจริง

---

## ข้อจำกัด v1.0 (ที่ honest แจ้งเลย)

- **สิกขาบทภิกษุณี 311 ข้อ** — Thera หาได้ 139 ข้อจากเล่ม 3 ที่เหลือ 172 ข้อ canon เก็บเป็น "อ้างถึงสิกขาบทภิกษุ" ใน vol 1-2 → Thera ไม่ขยายเอง ไม่หลอก surface เป็น diagnostic แทน (Reading B planned สำหรับ v1.x ถ้ามี mapping artifact คนทำมือ)
- **`thera verify` รองรับเฉพาะ Royal + MCU** — เพราะ 84000.org host แค่ 2 ฉบับนี้
- **อรรถกถา / ฎีกา ไม่รวม** — โครงการยึดหลัก "พระพุทธวจนะ" (canon เท่านั้น)

---

## Philosophy

โครงการนี้สร้างมาเพื่อตอบคำถาม:

> *"ทำยังไงให้ AI ใช้กับสิ่งศักดิ์สิทธิ์ได้โดยไม่หลอก?"*

คำตอบของ Thera = **ให้ AI ค้นเท่านั้น ไม่ให้สรุป** ผู้ใช้ได้สิ่งที่ canon **มี** ไม่ใช่สิ่งที่ AI **คิดว่า** canon น่าจะมี

ถ้า canon ไม่มี Thera **ไม่แต่งให้** ตามหลัก §1.4 abstain>guess (ยอมรับว่าไม่รู้ ดีกว่าหลอก)

นี่คือ pattern ที่อยากให้ propagate ไปใช้กับเอกสารอ่อนไหวอื่นๆ — กฎหมาย, พระคัมภีร์ศาสนาอื่น, เอกสารวิทยาศาสตร์ที่ผิดเพี้ยนไม่ได้

---

## เพิ่มเติม

- README ละเอียด: [README.th.md](../README.th.md)
- คู่มือเริ่มใช้: [QUICKSTART.th.md](QUICKSTART.th.md)
- Architecture (สำหรับ contributors): [ARCHITECTURE.th.md](ARCHITECTURE.th.md)
- Decision history (วิศวกรรม): [DESIGN_LOG.md](../DESIGN_LOG.md)

---

🪷 **สำหรับสาธุชน — Tool ที่เคารพพระไตรปิฎกตามตัวอักษร**
