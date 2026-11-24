/*
  DEV เท่านั้น -- ข้อมูลทดสอบ: ให้งวดค่าน้ำ/ค่าไฟ 10 งวดใน Contract_Installment_tr มีเลขตั้งหนี้ SAP
  เพื่อทดสอบว่าหน้าใบแจ้งหนี้ (/invoice/) แสดงรายการค่าน้ำ/ค่าไฟ ทั้งการค้นหาและหน้าพิมพ์

  ไม่ INSERT แถวใหม่ -- แก้เฉพาะ 3 คอลัมน์ของงวดที่มีอยู่แล้ว (เดิมทุกแถว: debt_to_SAP = '0', fi_doc/fi_date ว่าง)
  ถอนคืนด้วย 02_rollback_test_data.sql

  กรณีทดสอบ
    1. รวมกับใบแจ้งหนี้จริงเดิม (ค่าเช่าเดิม + ค่าน้ำ + ค่าไฟ ในใบเดียว)
         GRAD10/2567 (210) -> 2100000878,  J4/2566 (96) -> 2100000309
    2. ใบที่มีแต่ค่าน้ำ (SP เดิมคืนว่าง -- ระบบต้องสร้างหัวใบเอง)
         J6/2563 (39) -> TEST900001
    3. ใบที่มีค่าน้ำ + ค่าไฟ
         AD7/2563 (35) -> TEST900002,  D1/2563 (41) -> TEST900003
    4. ใบที่มีแต่ค่าไฟ (หนี้ประเภท 11)
         A123 (12) -> TEST900004
*/
SET XACT_ABORT ON;
SET NOCOUNT ON;

IF DB_NAME() <> N'SWU_contract' OR @@SERVERNAME <> N'DBDEV'
    THROW 50010, N'สคริปต์นี้ใช้กับ DEV (DBDEV / SWU_contract) เท่านั้น', 1;

DECLARE @Rows TABLE (
    Contract_id int, Contract_Installment_seq numeric(18, 0), Contract_type_price_id nvarchar(10),
    Fi_doc nvarchar(50), Fi_date date
);
INSERT INTO @Rows VALUES
 (210, 2,  N'9', N'2100000878', '2025-03-26'),
 (210, 3,  N'8', N'2100000878', '2025-03-26'),
 (96,  13, N'9', N'2100000309', '2023-10-31'),
 (96,  14, N'8', N'2100000309', '2023-10-31'),
 (39,  5,  N'8', N'TEST900001', '2026-11-20'),
 (35,  1,  N'9', N'TEST900002', '2026-11-20'),
 (35,  2,  N'8', N'TEST900002', '2026-11-20'),
 (41,  1,  N'9', N'TEST900003', '2026-11-20'),
 (41,  2,  N'8', N'TEST900003', '2026-11-20'),
 (12,  3,  N'9', N'TEST900004', '2026-11-20');

BEGIN TRANSACTION;

UPDATE i
SET i.Contract_debt_to_SAP = N'1',
    i.Contract_fi_doc = r.Fi_doc,
    i.Contract_fi_date = r.Fi_date
FROM dbo.Contract_Installment_tr i
INNER JOIN @Rows r
        ON r.Contract_id = i.Contract_id
       AND r.Contract_Installment_seq = i.Contract_Installment_seq
       AND r.Contract_type_price_id = i.Contract_type_price_id
WHERE i.Contract_fi_doc IS NULL;      -- ไม่ทับงวดที่มีเลข SAP อยู่แล้ว

IF @@ROWCOUNT <> 10
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50011, N'จำนวนแถวที่แก้ไม่ใช่ 10 -- ยกเลิกทั้งหมด (อาจรันซ้ำ หรือข้อมูล DEV เปลี่ยนไปแล้ว)', 1;
END

COMMIT TRANSACTION;

SELECT h.Contract_code, i.Contract_id, i.Contract_Installment_seq, i.Contract_type_price_id,
       i.Contract_Installment_month_year, i.Contract_Installment_amt,
       i.Contract_debt_to_SAP, i.Contract_fi_doc, i.Contract_fi_date
FROM dbo.Contract_Installment_tr i
INNER JOIN dbo.Contract_hrd_tr h ON h.Contract_id = i.Contract_id
INNER JOIN @Rows r
        ON r.Contract_id = i.Contract_id
       AND r.Contract_Installment_seq = i.Contract_Installment_seq
       AND r.Contract_type_price_id = i.Contract_type_price_id
ORDER BY i.Contract_fi_doc, i.Contract_type_price_id;
