# คอลัมน์ตั้งหนี้ค่าน้ำ-ค่าไฟ และคำอธิบายตารางมิเตอร์

## สิ่งที่เปลี่ยน

1. เพิ่มคอลัมน์ใน `Contract_meter_reading_tr` (ว่างได้ทั้งหมด ไม่มีค่า default)

   | คอลัมน์ | ชนิด | ความหมาย |
   |---|---|---|
   | `Amount` | `decimal(18,2)` | จำนวนเงินค่าน้ำ/ค่าไฟของรอบบิล |
   | `Contract_fi_doc` | `nvarchar(50)` | เลขที่เอกสารตั้งหนี้ SAP ว่าง = ยังไม่ตั้งหนี้ |
   | `Contract_fi_date` | `date` | วันที่ตั้งหนี้ SAP |
   | `Contract_debt_to_SAP` | `nvarchar(1)` | 0 = ยังไม่ตั้งหนี้, 1 = ตั้งหนี้แล้ว |
   | `contract_paid_id` | `int` | การชำระเงินผ่าน QR (`Contract_paid_hd_tr`) |
   | `Contract_receipt_number` | `nvarchar(50)` | เลขที่ใบเสร็จ |
   | `Contract_receipt_date` | `date` | วันที่ใบเสร็จ |

   ชนิดข้อมูลและคำอธิบายลอกจากคอลัมน์ชื่อเดียวกันใน `Contract_Installment_tr` (`Amount` เทียบกับ
   `Contract_Installment_amt`) และชื่อตรงกับที่
   view `v_contract_price_tr_F22_3` เตรียมไว้ (ส่วนที่คอมเมนต์ "ปิดไว้ก่อนรอสร้างฟิลด์ 2026-11-16")

2. ใส่คำอธิบาย `MS_Description` ของตารางและทุกคอลัมน์ใน
   `Contract_meter_ms`, `Contract_meter_tr`, `Contract_meter_reading_tr`, `Contract_meter_phase_ms`
   (เห็นใน SSMS ที่ Properties ของตาราง/คอลัมน์)

ไม่แก้ SP, view หรือข้อมูลเดิม -- `sp_Contract_Meter_Reading_Save` INSERT แบบระบุคอลัมน์ จึงทำงานได้เหมือนเดิม
ยังไม่มีโปรแกรมเขียนค่าลงคอลัมน์ใหม่ และยังต้องเปิดส่วนที่คอมเมนต์ไว้ใน `v_contract_price_tr_F22_3` เอง

## ไฟล์

1. `01_apply_meter_billing_columns.sql` — เพิ่มคอลัมน์และคำอธิบาย รันซ้ำได้ ท้ายไฟล์แสดงผลตรวจ
2. `02_rollback_meter_billing_columns.sql` — ถอนคอลัมน์ใหม่ ยกเลิกเองถ้ามีข้อมูลในคอลัมน์ใหม่แล้ว

## ประวัติการรัน

- 2026-11-24 DEV (`DBDEV` / `SWU_contract`) — รัน `01` แล้ว 3 รอบ (รอบสามเพิ่ม 4 คอลัมน์หลัง
  รันซ้ำไม่เปลี่ยนสิ่งที่มีอยู่)
  `02` ตรวจ syntax ด้วย `SET NOEXEC ON` เท่านั้น ยังไม่เคยรันจริง
- PRD — ยังไม่ได้รัน
