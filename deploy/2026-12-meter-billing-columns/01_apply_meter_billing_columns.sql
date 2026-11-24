/*
  เพิ่มคอลัมน์ตั้งหนี้ค่าน้ำ-ค่าไฟใน Contract_meter_reading_tr และคำอธิบาย (MS_Description)
  ของตารางมิเตอร์ 4 ตาราง -- รันซ้ำได้ (ตรวจก่อนเพิ่มทุกจุด)

  คอลัมน์ใหม่ (ว่างได้ทั้งหมด ไม่มีค่า default ไม่กระทบ SP เดิมที่ INSERT แบบระบุคอลัมน์):
    Amount           decimal(18,2)  จำนวนเงินของรอบบิล -- ชนิดเดียวกับ Contract_Installment_tr.Contract_Installment_amt
    Contract_fi_doc  nvarchar(50)   เลขที่เอกสารตั้งหนี้ SAP -- ชนิดเดียวกับ Contract_Installment_tr.Contract_fi_doc
    Contract_fi_date date           วันที่ตั้งหนี้ SAP -- ชนิดเดียวกับ Contract_Installment_tr.Contract_fi_date
    Contract_debt_to_SAP    nvarchar(1)  0 = ยังไม่ตั้งหนี้, 1 = ตั้งหนี้แล้ว
    contract_paid_id        int          การชำระเงินผ่าน QR (Contract_paid_hd_tr)
    Contract_receipt_number nvarchar(50) เลขที่ใบเสร็จ
    Contract_receipt_date   date         วันที่ใบเสร็จ
  ชื่อ ชนิด และคำอธิบายลอกจาก Contract_Installment_tr (ไม่ลอก default -- ต้นฉบับก็ไม่มี)
  ชื่อตรงกับที่ view v_contract_price_tr_F22_3 เตรียมไว้ (rd.amount / rd.Contract_fi_doc / rd.Contract_fi_date)
*/
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Amount') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Amount decimal(18, 2) NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Contract_fi_doc') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Contract_fi_doc nvarchar(50) NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Contract_fi_date') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Contract_fi_date date NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Contract_debt_to_SAP') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Contract_debt_to_SAP nvarchar(1) NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'contract_paid_id') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD contract_paid_id int NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Contract_receipt_number') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Contract_receipt_number nvarchar(50) NULL;
IF COL_LENGTH('dbo.Contract_meter_reading_tr', 'Contract_receipt_date') IS NULL
    ALTER TABLE dbo.Contract_meter_reading_tr ADD Contract_receipt_date date NULL;

COMMIT TRANSACTION;
GO

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @Desc TABLE (TableName sysname, ColumnName sysname NULL, Description nvarchar(400));
INSERT INTO @Desc (TableName, ColumnName, Description) VALUES
 -- Contract_meter_ms
 (N'Contract_meter_ms', NULL, N'ทะเบียนมิเตอร์น้ำ-ไฟ หนึ่งแถวต่อมิเตอร์หนึ่งตัว ติดตั้งอยู่ในพื้นที่ย่อย (SubArea)'),
 (N'Contract_meter_ms', N'Meter_id', N'รหัสมิเตอร์ (รันอัตโนมัติ คีย์หลัก)'),
 (N'Contract_meter_ms', N'Location_id', N'รหัสสถานที่ (Contract_location_ms)'),
 (N'Contract_meter_ms', N'Area_id', N'รหัสพื้นที่ (Contract_location_area_ms)'),
 (N'Contract_meter_ms', N'SubArea_id', N'รหัสพื้นที่ย่อยที่ติดตั้งมิเตอร์ (Contract_location_subarea_ms)'),
 (N'Contract_meter_ms', N'Meter_type_cd', N'ประเภทมิเตอร์ 9 = น้ำประปา, 8 = ไฟฟ้า (สลับกับรหัสค่าใช้จ่ายใน Contract_type_price_ms ที่ 8 = ค่าน้ำ, 9 = ค่าไฟ)'),
 (N'Contract_meter_ms', N'Meter_seq', N'ลำดับมิเตอร์ในพื้นที่ย่อยและประเภทเดียวกัน (ไม่ซ้ำตาม SubArea_id + Meter_type_cd + Meter_seq)'),
 (N'Contract_meter_ms', N'Meter_no', N'เลขมิเตอร์'),
 (N'Contract_meter_ms', N'Meter_no_status', N'สถานะเลขมิเตอร์ เช่น ปกติ, รอ Gen เลข'),
 (N'Contract_meter_ms', N'Phase_type', N'ระบบไฟฟ้าของมิเตอร์ไฟฟ้า (Contract_meter_phase_ms.Phase_type)'),
 (N'Contract_meter_ms', N'UseOrNot', N'1 = ใช้งาน, 0 = ยกเลิกใช้งาน'),
 (N'Contract_meter_ms', N'Meter_remark', N'หมายเหตุ'),
 (N'Contract_meter_ms', N'UserEntry', N'ผู้บันทึก'),
 (N'Contract_meter_ms', N'DateEntry', N'วันเวลาที่บันทึก'),
 (N'Contract_meter_ms', N'UserUpdate', N'ผู้แก้ไขล่าสุด'),
 (N'Contract_meter_ms', N'DateUpdate', N'วันเวลาที่แก้ไขล่าสุด'),
 (N'Contract_meter_ms', N'Meter_image_url', N'URL รูปมิเตอร์'),
 -- Contract_meter_tr
 (N'Contract_meter_tr', NULL, N'การผูกมิเตอร์กับสัญญา ระบุว่าสัญญาใช้มิเตอร์ตัวไหนในพื้นที่ใด (ไม่ซ้ำตาม Contract_id + Meter_id)'),
 (N'Contract_meter_tr', N'Contract_meter_seq', N'ลำดับรายการ (รันอัตโนมัติ คีย์หลัก)'),
 (N'Contract_meter_tr', N'Contract_id', N'รหัสสัญญา (Contract_hrd_tr.Contract_id)'),
 (N'Contract_meter_tr', N'Location_id', N'รหัสสถานที่ของพื้นที่ตามสัญญา'),
 (N'Contract_meter_tr', N'Area_id', N'รหัสพื้นที่ตามสัญญา'),
 (N'Contract_meter_tr', N'SubArea_id', N'รหัสพื้นที่ย่อยตามสัญญา'),
 (N'Contract_meter_tr', N'Meter_id', N'รหัสมิเตอร์ (Contract_meter_ms.Meter_id)'),
 (N'Contract_meter_tr', N'UseOrNot', N'1 = ผูกอยู่และคิดค่าน้ำ-ไฟ, 0 = เลิกผูก (เช่น ยกเลิกสัญญาและปิดการคิดค่ามิเตอร์)'),
 (N'Contract_meter_tr', N'UserEntry', N'ผู้บันทึก'),
 (N'Contract_meter_tr', N'DateEntry', N'วันเวลาที่บันทึก'),
 (N'Contract_meter_tr', N'UserUpdate', N'ผู้แก้ไขล่าสุด'),
 (N'Contract_meter_tr', N'DateUpdate', N'วันเวลาที่แก้ไขล่าสุด'),
 -- Contract_meter_reading_tr
 (N'Contract_meter_reading_tr', NULL, N'เลขอ่านมิเตอร์รายรอบบิล หนึ่งแถวต่อมิเตอร์ต่อเดือน (ไม่ซ้ำตาม Meter_id + Billing_year_be + Billing_month) พร้อมจำนวนเงินและเลขตั้งหนี้ SAP'),
 (N'Contract_meter_reading_tr', N'Reading_id', N'รหัสรายการ (รันอัตโนมัติ คีย์หลัก)'),
 (N'Contract_meter_reading_tr', N'Meter_id', N'รหัสมิเตอร์ (Contract_meter_ms.Meter_id)'),
 (N'Contract_meter_reading_tr', N'Billing_year_be', N'ปีของรอบบิล (พ.ศ.)'),
 (N'Contract_meter_reading_tr', N'Billing_month', N'เดือนของรอบบิล (1-12)'),
 (N'Contract_meter_reading_tr', N'Reading_before', N'เลขอ่านครั้งก่อน'),
 (N'Contract_meter_reading_tr', N'Reading_after', N'เลขอ่านครั้งนี้'),
 (N'Contract_meter_reading_tr', N'UserEntry', N'ผู้บันทึก'),
 (N'Contract_meter_reading_tr', N'DateEntry', N'วันเวลาที่บันทึก'),
 (N'Contract_meter_reading_tr', N'UserUpdate', N'ผู้แก้ไขล่าสุด'),
 (N'Contract_meter_reading_tr', N'DateUpdate', N'วันเวลาที่แก้ไขล่าสุด'),
 (N'Contract_meter_reading_tr', N'Contract_id', N'รหัสสัญญาที่มิเตอร์ผูกอยู่ตอนบันทึกเลขอ่าน (snapshot)'),
 (N'Contract_meter_reading_tr', N'Contract_code', N'รหัสสัญญาตอนบันทึกเลขอ่าน (snapshot)'),
 (N'Contract_meter_reading_tr', N'Amount', N'จำนวนเงินค่าน้ำ/ค่าไฟของรอบบิลนี้ (บาท) สำหรับส่งตั้งหนี้ SAP'),
 (N'Contract_meter_reading_tr', N'Contract_fi_doc', N'เลขที่เอกสารตั้งหนี้จาก SAP (แบบเดียวกับ Contract_Installment_tr.Contract_fi_doc) ว่าง = ยังไม่ได้ตั้งหนี้'),
 (N'Contract_meter_reading_tr', N'Contract_fi_date', N'วันที่ตั้งหนี้ใน SAP (แบบเดียวกับ Contract_Installment_tr.Contract_fi_date)'),
 (N'Contract_meter_reading_tr', N'Contract_debt_to_SAP', N'0=ยังไม่ตั้งหนี้ 1=ตั้งหนี้ (แบบเดียวกับ Contract_Installment_tr.Contract_debt_to_SAP)'),
 (N'Contract_meter_reading_tr', N'contract_paid_id', N'การชำระเงินจาก โอน QR code (Contract_paid_hd_tr)'),
 (N'Contract_meter_reading_tr', N'Contract_receipt_number', N'เลขที่ใบเสร็จ (24XXXXXXX)'),
 (N'Contract_meter_reading_tr', N'Contract_receipt_date', N'วันที่ใบเสร็จ'),
 -- Contract_meter_phase_ms
 (N'Contract_meter_phase_ms', NULL, N'Master ระบบไฟฟ้า (เฟส) สำหรับมิเตอร์ไฟฟ้า'),
 (N'Contract_meter_phase_ms', N'Phase_id', N'รหัสระบบไฟฟ้า (รันอัตโนมัติ คีย์หลัก)'),
 (N'Contract_meter_phase_ms', N'Phase_type', N'ชื่อระบบไฟฟ้า เป็นค่าที่บันทึกลง Contract_meter_ms.Phase_type (ไม่ซ้ำ)'),
 (N'Contract_meter_phase_ms', N'Phase_desc', N'คำอธิบายระบบไฟฟ้า'),
 (N'Contract_meter_phase_ms', N'UseOrNot', N'1 = ใช้งาน, 0 = ยกเลิกใช้งาน'),
 (N'Contract_meter_phase_ms', N'UserEntry', N'ผู้บันทึก'),
 (N'Contract_meter_phase_ms', N'DateEntry', N'วันเวลาที่บันทึก'),
 (N'Contract_meter_phase_ms', N'UserUpdate', N'ผู้แก้ไขล่าสุด'),
 (N'Contract_meter_phase_ms', N'DateUpdate', N'วันเวลาที่แก้ไขล่าสุด');

DECLARE @t sysname, @c sysname, @d nvarchar(400);
DECLARE desc_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT TableName, ColumnName, Description FROM @Desc;
OPEN desc_cursor;
FETCH NEXT FROM desc_cursor INTO @t, @c, @d;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF @c IS NULL
    BEGIN
        IF EXISTS (SELECT 1 FROM sys.extended_properties
                   WHERE major_id = OBJECT_ID(N'dbo.' + @t) AND minor_id = 0 AND name = N'MS_Description')
            EXEC sys.sp_updateextendedproperty @name = N'MS_Description', @value = @d,
                 @level0type = N'SCHEMA', @level0name = N'dbo', @level1type = N'TABLE', @level1name = @t;
        ELSE
            EXEC sys.sp_addextendedproperty @name = N'MS_Description', @value = @d,
                 @level0type = N'SCHEMA', @level0name = N'dbo', @level1type = N'TABLE', @level1name = @t;
    END
    ELSE
    BEGIN
        IF COL_LENGTH(N'dbo.' + @t, @c) IS NULL
            THROW 50001, N'ไม่พบคอลัมน์ที่จะใส่คำอธิบาย -- ตรวจชื่อตาราง/คอลัมน์', 1;
        IF EXISTS (SELECT 1 FROM sys.extended_properties
                   WHERE major_id = OBJECT_ID(N'dbo.' + @t) AND name = N'MS_Description'
                     AND minor_id = COLUMNPROPERTY(OBJECT_ID(N'dbo.' + @t), @c, 'ColumnId'))
            EXEC sys.sp_updateextendedproperty @name = N'MS_Description', @value = @d,
                 @level0type = N'SCHEMA', @level0name = N'dbo', @level1type = N'TABLE', @level1name = @t,
                 @level2type = N'COLUMN', @level2name = @c;
        ELSE
            EXEC sys.sp_addextendedproperty @name = N'MS_Description', @value = @d,
                 @level0type = N'SCHEMA', @level0name = N'dbo', @level1type = N'TABLE', @level1name = @t,
                 @level2type = N'COLUMN', @level2name = @c;
    END
    FETCH NEXT FROM desc_cursor INTO @t, @c, @d;
END
CLOSE desc_cursor;
DEALLOCATE desc_cursor;

COMMIT TRANSACTION;
GO

-- ตรวจผล
SELECT t.name AS TableName, c.name AS ColumnName, TYPE_NAME(c.user_type_id) AS DataType,
       c.precision, c.scale, c.max_length, CAST(ep.value AS nvarchar(400)) AS Description
FROM sys.tables t
LEFT JOIN sys.columns c ON c.object_id = t.object_id
LEFT JOIN sys.extended_properties ep
       ON ep.major_id = t.object_id AND ep.minor_id = c.column_id AND ep.name = N'MS_Description'
WHERE t.name IN (N'Contract_meter_ms', N'Contract_meter_tr', N'Contract_meter_reading_tr', N'Contract_meter_phase_ms')
ORDER BY t.name, c.column_id;
