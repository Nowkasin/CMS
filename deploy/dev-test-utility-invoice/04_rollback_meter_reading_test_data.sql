/*
  DEV เท่านั้น -- ถอนข้อมูลทดสอบของ 03_apply_meter_reading_test_data.sql
  คืน 6 เลขอ่านเป็นค่าว่าง (Amount / debt_to_SAP / fi_doc / fi_date) เฉพาะแถวที่ยังมีเลขทดสอบ รันซ้ำได้
*/
SET XACT_ABORT ON;
SET NOCOUNT ON;

IF DB_NAME() <> N'SWU_contract' OR @@SERVERNAME <> N'DBDEV'
    THROW 50010, N'สคริปต์นี้ใช้กับ DEV (DBDEV / SWU_contract) เท่านั้น', 1;

BEGIN TRANSACTION;

UPDATE dbo.Contract_meter_reading_tr
SET Amount = NULL,
    Contract_debt_to_SAP = NULL,
    Contract_fi_doc = NULL,
    Contract_fi_date = NULL
WHERE Reading_id IN (38, 27, 35, 36, 24, 25)
  AND Contract_fi_doc IN (N'TEST900101', N'TEST900102', N'TEST900103', N'TEST900104');

SELECT @@ROWCOUNT AS restored_rows;

COMMIT TRANSACTION;
