/*
  DEV เท่านั้น -- ถอนข้อมูลทดสอบของ 01_apply_test_data.sql
  คืน 10 งวดเป็นค่าเดิม (debt_to_SAP = '0', fi_doc/fi_date ว่าง)
  แก้เฉพาะแถวที่ยังมีเลขตามที่สคริปต์ทดสอบใส่ไว้ จึงรันซ้ำได้
*/
SET XACT_ABORT ON;
SET NOCOUNT ON;

IF DB_NAME() <> N'SWU_contract' OR @@SERVERNAME <> N'DBDEV'
    THROW 50010, N'สคริปต์นี้ใช้กับ DEV (DBDEV / SWU_contract) เท่านั้น', 1;

DECLARE @Rows TABLE (
    Contract_id int, Contract_Installment_seq numeric(18, 0), Contract_type_price_id nvarchar(10),
    Fi_doc nvarchar(50)
);
INSERT INTO @Rows VALUES
 (210, 2,  N'9', N'2100000878'),
 (210, 3,  N'8', N'2100000878'),
 (96,  13, N'9', N'2100000309'),
 (96,  14, N'8', N'2100000309'),
 (39,  5,  N'8', N'TEST900001'),
 (35,  1,  N'9', N'TEST900002'),
 (35,  2,  N'8', N'TEST900002'),
 (41,  1,  N'9', N'TEST900003'),
 (41,  2,  N'8', N'TEST900003'),
 (12,  3,  N'9', N'TEST900004');

BEGIN TRANSACTION;

UPDATE i
SET i.Contract_debt_to_SAP = N'0',
    i.Contract_fi_doc = NULL,
    i.Contract_fi_date = NULL
FROM dbo.Contract_Installment_tr i
INNER JOIN @Rows r
        ON r.Contract_id = i.Contract_id
       AND r.Contract_Installment_seq = i.Contract_Installment_seq
       AND r.Contract_type_price_id = i.Contract_type_price_id
       AND r.Fi_doc = i.Contract_fi_doc;

SELECT @@ROWCOUNT AS restored_rows;

COMMIT TRANSACTION;
