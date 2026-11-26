/*
  DEV เท่านั้น -- ข้อมูลทดสอบบรรทัดค่าน้ำ/ค่าไฟจากเลขอ่านมิเตอร์ (Contract_meter_reading_tr)
  ใส่ Amount / เลขตั้งหนี้ SAP ให้เลขอ่านเดือน ก.ย. 2569 จำนวน 6 มิเตอร์ ถอนคืนด้วย 04_rollback

  กรณีทดสอบ
    1. A4/2569 (228) -- รวมกับใบจริงวันที่ 1 มิ.ย. 2569 (ค่าเช่า + ค่าธรรมเนียมรายปี + ค่าประกัน)
       ได้ใบแบบเดียวกับแบบร่างหน้า 1 (5 บรรทัด มีเลขมิเตอร์ก่อน/หลังที่ค่าไฟ ค่าน้ำ)
    2. AI5-AI6/2569 (226) -- มิเตอร์ไฟ 2 ตัว น้ำ 2 ตัว ได้ 4 บรรทัด (หนึ่งบรรทัดต่อมิเตอร์)
*/
SET XACT_ABORT ON;
SET NOCOUNT ON;

IF DB_NAME() <> N'SWU_contract' OR @@SERVERNAME <> N'DBDEV'
    THROW 50010, N'สคริปต์นี้ใช้กับ DEV (DBDEV / SWU_contract) เท่านั้น', 1;

DECLARE @Rows TABLE (Reading_id int, Amount decimal(18, 2), Fi_doc nvarchar(50), Fi_date date);
INSERT INTO @Rows VALUES
 (38, 492.00,  N'TEST900101', '2026-06-01'),   -- A4/2569 ไฟ
 (27, 600.00,  N'TEST900102', '2026-06-01'),   -- A4/2569 น้ำ
 (35, 1092.00, N'TEST900103', '2026-11-20'),   -- AI5-AI6/2569 ไฟ ตัวที่ 1
 (36, 1902.00, N'TEST900103', '2026-11-20'),   -- AI5-AI6/2569 ไฟ ตัวที่ 2
 (24, 140.00,  N'TEST900104', '2026-11-20'),   -- AI5-AI6/2569 น้ำ ตัวที่ 1
 (25, 260.00,  N'TEST900104', '2026-11-20');   -- AI5-AI6/2569 น้ำ ตัวที่ 2

BEGIN TRANSACTION;

UPDATE rd
SET rd.Amount = r.Amount,
    rd.Contract_debt_to_SAP = N'1',
    rd.Contract_fi_doc = r.Fi_doc,
    rd.Contract_fi_date = r.Fi_date
FROM dbo.Contract_meter_reading_tr rd
INNER JOIN @Rows r ON r.Reading_id = rd.Reading_id
WHERE rd.Contract_fi_doc IS NULL AND rd.Amount IS NULL;

IF @@ROWCOUNT <> 6
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50011, N'จำนวนแถวที่แก้ไม่ใช่ 6 -- ยกเลิกทั้งหมด (อาจรันซ้ำ หรือข้อมูล DEV เปลี่ยนไปแล้ว)', 1;
END

COMMIT TRANSACTION;

SELECT rd.Reading_id, rd.Contract_code, rd.Meter_id, rd.Billing_year_be, rd.Billing_month,
       rd.Reading_before, rd.Reading_after, rd.Amount, rd.Contract_debt_to_SAP, rd.Contract_fi_doc, rd.Contract_fi_date
FROM dbo.Contract_meter_reading_tr rd
INNER JOIN @Rows r ON r.Reading_id = rd.Reading_id
ORDER BY rd.Reading_id;
