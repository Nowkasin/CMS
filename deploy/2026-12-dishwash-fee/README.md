# เมนู "ค่าล้างจาน"

บันทึกยอดค่าล้างจานรายเดือนต่อสัญญา ผู้ใช้กรอกยอดเอง (ผู้ใช้กำหนด 2026-11-26 -- ไม่มีฟอร์มเดิมใน K2)
หน้า CMS: `/dishwash/` (`meters/views/dishwash.py`, `meters/services/dishwash.py`)

## สิ่งที่สคริปต์สร้าง

1. **ตาราง `dbo.Contract_dishwash_tr`** -- 1 แถวต่อสัญญาต่อรอบบิล
   - `UNIQUE (Contract_id, Billing_year_be, Billing_month)`, FK ไป `Contract_hrd_tr`
   - `Amount decimal(18,2)` ห้ามติดลบ, `Billing_month` 1-12
   - คอลัมน์ตั้งหนี้/ใบเสร็จชุดเดียวกับ `Contract_meter_reading_tr`
     (`Contract_debt_to_SAP`, `Contract_fi_doc`, `Contract_fi_date`, `contract_paid_id`,
     `Contract_receipt_number`, `Contract_receipt_date`)
   - MS_Description ครบทุกคอลัมน์
2. **ประเภทค่าใช้จ่าย `11` ค่าล้างจาน** ใน `Contract_type_price_ms` (รหัสจัดสรร/ระดับ `1`/`1` เหมือนค่าน้ำ ค่าไฟ)
   -- ใช้เป็นชื่อบรรทัดในใบแจ้งหนี้ ประเภทนี้จะโผล่ในตัวเลือกประเภทค่าใช้จ่ายของฟอร์ม K2 ด้วย
3. **เมนู K2 `dishwash_fee`** "ค่าล้างจาน" ใต้ `water_electric_new` (OrderNo 9) + สิทธิ์ 3 กลุ่ม:
   ทดสอบ หลังบ้านตั้งหนี้ CMS, SAP / ทดสอบ หน้าบ้านสร้างสัญญา / ผู้ดูแลระบบ ( Admin )

## พฤติกรรมของหน้า

- แสดงสัญญาที่สถานะไม่ใช่ ไม่ต่อสัญญา / ยกเลิก / ปิดสัญญา (+ สัญญาที่มียอดรอบนั้นอยู่แล้ว)
- ล้างช่องยอดแล้วบันทึก = ลบรายการของรอบนั้น
- รายการที่ `Contract_fi_doc` มีค่า (ตั้งหนี้ SAP แล้ว) แก้/ลบจาก CMS ไม่ได้
- รายการที่ตั้งหนี้แล้วขึ้นในใบแจ้งหนี้เป็นบรรทัด "ค่าล้างจาน"
- **ยังไม่มี** ขั้นตอนส่งค่าล้างจานไปตั้งหนี้ SAP (view `v_contract_price_tr_F22_3` ยังไม่รวมตารางนี้)
  -- `Contract_fi_doc` จึงยังว่างจนกว่าจะทำส่วนนั้น

## ไฟล์

1. `01_apply_dishwash_fee.sql` — สร้างตาราง/ประเภท/เมนู/สิทธิ์ ใน Transaction เดียว รันซ้ำได้
2. `02_rollback_dishwash_fee.sql` — ปิดเมนูและสิทธิ์ (ไม่ลบแถว), ลบตารางเฉพาะเมื่อยังว่าง,
   ลบประเภท 11 เฉพาะเมื่อไม่มีตารางใดอ้างอิง

## ลำดับติดตั้ง

1. ต้องมีเมนูหลัก `water_electric_new` แล้ว (`deploy/2026-11-cms-menu`)
2. แก้ `@CmsBaseUrl` ให้ตรงกับ URL จริง และตรวจ GroupId บน PRD
3. Deploy โค้ดรุ่นที่มีหน้า `/dishwash/` แล้วรัน `collectstatic`
4. รัน `01_apply_dishwash_fee.sql`
5. ผู้ใช้เห็นเมนูภายใน 10 นาที (`CMS_ACCESS_REFRESH_SECONDS`) หรือออกจากระบบแล้วเข้าใหม่

## ประวัติการรัน

- 2026-11-26 DEV (`DBDEV` / `SWU_contract`) — รันแล้ว (menuId 92) `@CmsBaseUrl` ใช้ฐาน URL เดียวกับเมนูใบแจ้งหนี้บน DEV
- PRD — ยังไม่ได้รัน
