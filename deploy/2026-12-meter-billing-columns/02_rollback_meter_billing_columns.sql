/*
  ถอนคอลัมน์ Amount / Contract_fi_doc / Contract_fi_date / Contract_debt_to_SAP / contract_paid_id /
  Contract_receipt_number / Contract_receipt_date ออกจาก Contract_meter_reading_tr
  -- ยกเลิกเองถ้ามีข้อมูลในคอลัมน์ใดแล้ว เพื่อไม่ให้จำนวนเงินหรือเลขตั้งหนี้ SAP หาย
  คำอธิบาย (MS_Description) ของคอลัมน์อื่นและตารางคงไว้ เพราะเป็นเอกสารประกอบ ไม่กระทบการทำงาน
*/
SET XACT_ABORT ON;

-- ตรวจผ่าน dynamic SQL เพราะถ้าคอลัมน์ถูกถอนไปแล้ว การอ้างชื่อตรงๆ จะ compile ไม่ผ่านทั้ง batch
DECLARE @has_data bit = 0, @col sysname, @sql nvarchar(400);
DECLARE chk CURSOR LOCAL FAST_FORWARD FOR
    SELECT v.c FROM (VALUES (N'Amount'), (N'Contract_fi_doc'), (N'Contract_fi_date'), (N'Contract_debt_to_SAP'),
                            (N'contract_paid_id'), (N'Contract_receipt_number'), (N'Contract_receipt_date')) v(c);
OPEN chk;
FETCH NEXT FROM chk INTO @col;
WHILE @@FETCH_STATUS = 0 AND @has_data = 0
BEGIN
    IF COL_LENGTH(N'dbo.Contract_meter_reading_tr', @col) IS NOT NULL
    BEGIN
        -- @col มาจากรายการคงที่ด้านบนเท่านั้น
        SET @sql = N'SELECT @h = CASE WHEN EXISTS (SELECT 1 FROM dbo.Contract_meter_reading_tr WHERE '
                 + QUOTENAME(@col) + N' IS NOT NULL) THEN 1 ELSE 0 END';
        EXEC sys.sp_executesql @sql, N'@h bit OUTPUT', @h = @has_data OUTPUT;
    END
    FETCH NEXT FROM chk INTO @col;
END
CLOSE chk;
DEALLOCATE chk;
IF @has_data = 1
    THROW 50002, N'มีข้อมูลจำนวนเงิน/เลขตั้งหนี้แล้ว -- ไม่ถอนคอลัมน์ ให้สำรองข้อมูลและตัดสินใจก่อน', 1;
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @c sysname, @drop nvarchar(400);
DECLARE col_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT v.c FROM (VALUES (N'Amount'), (N'Contract_fi_doc'), (N'Contract_fi_date'), (N'Contract_debt_to_SAP'),
                            (N'contract_paid_id'), (N'Contract_receipt_number'), (N'Contract_receipt_date')) v(c);
OPEN col_cursor;
FETCH NEXT FROM col_cursor INTO @c;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF COL_LENGTH(N'dbo.Contract_meter_reading_tr', @c) IS NOT NULL
    BEGIN
        IF EXISTS (SELECT 1 FROM sys.extended_properties
                   WHERE major_id = OBJECT_ID(N'dbo.Contract_meter_reading_tr') AND name = N'MS_Description'
                     AND minor_id = COLUMNPROPERTY(OBJECT_ID(N'dbo.Contract_meter_reading_tr'), @c, 'ColumnId'))
            EXEC sys.sp_dropextendedproperty @name = N'MS_Description',
                 @level0type = N'SCHEMA', @level0name = N'dbo',
                 @level1type = N'TABLE', @level1name = N'Contract_meter_reading_tr',
                 @level2type = N'COLUMN', @level2name = @c;
        SET @drop = N'ALTER TABLE dbo.Contract_meter_reading_tr DROP COLUMN ' + QUOTENAME(@c);   -- @c มาจากรายการคงที่ด้านบนเท่านั้น
        EXEC sys.sp_executesql @drop;
    END
    FETCH NEXT FROM col_cursor INTO @c;
END
CLOSE col_cursor;
DEALLOCATE col_cursor;

COMMIT TRANSACTION;
GO
