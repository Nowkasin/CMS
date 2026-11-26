-- เมนู "ค่าล้างจาน": บันทึกยอดค่าล้างจานรายเดือนต่อสัญญา (ผู้ใช้กำหนด 2026-11-26)
--   1) ตาราง dbo.Contract_dishwash_tr -- 1 แถวต่อสัญญาต่อรอบบิล คอลัมน์ตั้งหนี้/ใบเสร็จแบบเดียวกับ
--      Contract_meter_reading_tr (deploy/2026-12-meter-billing-columns)
--   2) ประเภทค่าใช้จ่าย '11' ค่าล้างจาน ใน Contract_type_price_ms (ใช้ชื่อในใบแจ้งหนี้)
--   3) เมนู K2 key dishwash_fee ใต้ water_electric_new + สิทธิ์ 3 กลุ่ม
-- ไม่แก้ตารางเดิม ไม่แก้งวดใน Contract_Installment_tr รันซ้ำได้ ผู้ดูแลฐานข้อมูลเป็นผู้รัน
-- ไม่มี GO -- รันเป็น batch เดียวได้ทั้งใน SSMS และจากโปรแกรม (CREATE TABLE ใช้ dynamic SQL)
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

-- ต้องแก้เป็น URL จริงก่อนรัน ให้ตรงกับเมนูอื่นของ CMS (ดู deploy/2026-11-cms-menu)
DECLARE @CmsBaseUrl nvarchar(500) = N'https://CHANGE-ME.example/cms';
DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @MenuKey nvarchar(100) = N'dishwash_fee';
DECLARE @IconUrl nvarchar(500) = N'/Runtime/Styles/Themes/Platinum/ico-quotation-request.png';
-- กลุ่มที่เห็นเมนู (GroupId ตรวจจาก SysGroup บน DEV แล้ว -- ตรวจซ้ำบน PRD ก่อนรัน)
--   00B67BB6-... = ทดสอบ หลังบ้านตั้งหนี้ CMS, SAP
--   31200B53-... = ทดสอบ หน้าบ้านสร้างสัญญา
--   9B148353-... = ผู้ดูแลระบบ ( Admin )
DECLARE @Groups table (GroupId uniqueidentifier NOT NULL PRIMARY KEY);
INSERT INTO @Groups (GroupId) VALUES
    ('00B67BB6-1982-400F-BA50-33CF8FA36D3E'),
    ('31200B53-36EC-47A1-88F2-4463A597C0F9'),
    ('9B148353-6383-40D7-B3B8-F04FC8C5A4C5');

IF @CmsBaseUrl LIKE N'%CHANGE-ME%'
    THROW 50001, N'กรุณากำหนด @CmsBaseUrl เป็น URL จริงก่อนรัน', 1;
WHILE RIGHT(@CmsBaseUrl, 1) = N'/'
    SET @CmsBaseUrl = LEFT(@CmsBaseUrl, LEN(@CmsBaseUrl) - 1);

DECLARE @RootMenuId int;
SELECT @RootMenuId = menuId FROM dbo.Sysmenu WHERE menu_name_eng = @RootKey AND IsActive = 1;
IF @RootMenuId IS NULL
    THROW 50002, N'ไม่พบเมนูหลัก water_electric_new -- ต้องติดตั้ง deploy/2026-11-cms-menu ก่อน', 1;

IF EXISTS (
    SELECT 1 FROM @Groups g LEFT JOIN dbo.SysGroup s ON s.GroupId = g.GroupId
    WHERE s.GroupId IS NULL OR ISNULL(s.IsActive, 0) <> 1
)
    THROW 50003, N'พบ GroupId ที่ไม่มีอยู่หรือไม่ได้เปิดใช้งาน', 1;

-- ประเภท 11 ต้องยังไม่ถูกใช้เป็นอย่างอื่น
IF EXISTS (SELECT 1 FROM dbo.Contract_type_price_ms
           WHERE Contract_type_price_id = N'11' AND Contract_type_price_desc <> N'ค่าล้างจาน')
    THROW 50005, N'Contract_type_price_id 11 ถูกใช้เป็นประเภทอื่นแล้ว -- ต้องเลือกเลขใหม่', 1;

DECLARE @MenuId int;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.Contract_dishwash_tr', N'U') IS NULL
    BEGIN
        EXEC sys.sp_executesql N'
        CREATE TABLE dbo.Contract_dishwash_tr (
            Dishwash_id             int IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_Contract_dishwash_tr PRIMARY KEY,
            Contract_id             int NOT NULL
                CONSTRAINT FK_Contract_dishwash_tr_Contract REFERENCES dbo.Contract_hrd_tr (Contract_id),
            Contract_code           nvarchar(30) NULL,
            Billing_year_be         int NOT NULL,
            Billing_month           tinyint NOT NULL
                CONSTRAINT CK_Contract_dishwash_tr_Month CHECK (Billing_month BETWEEN 1 AND 12),
            Amount                  decimal(18, 2) NOT NULL
                CONSTRAINT CK_Contract_dishwash_tr_Amount CHECK (Amount >= 0),
            Remark                  nvarchar(500) NULL,
            Contract_debt_to_SAP    nvarchar(1) NULL,
            Contract_fi_doc         nvarchar(50) NULL,
            Contract_fi_date        date NULL,
            contract_paid_id        int NULL,
            Contract_receipt_number nvarchar(50) NULL,
            Contract_receipt_date   date NULL,
            UserEntry               nvarchar(100) NULL,
            DateEntry               datetime NULL,
            UserUpdate              nvarchar(100) NULL,
            DateUpdate              datetime NULL,
            CONSTRAINT UQ_Contract_dishwash_tr_ContractPeriod
                UNIQUE (Contract_id, Billing_year_be, Billing_month)
        );
        CREATE INDEX IX_Contract_dishwash_tr_Period
            ON dbo.Contract_dishwash_tr (Billing_year_be, Billing_month);';
    END;

    IF NOT EXISTS (SELECT 1 FROM dbo.Contract_type_price_ms WHERE Contract_type_price_id = N'11')
        INSERT INTO dbo.Contract_type_price_ms (
            Contract_type_price_id, Contract_type_price_desc, Contract_status_allocate_cd,
            Contract_pre_location_or_contract, UserEntry, DateEntry
        )
        -- รหัสจัดสรร/ระดับเหมือนค่าน้ำ ค่าไฟ (1, 1) เพราะคิดรายเดือนตามการใช้งานเหมือนกัน
        VALUES (N'11', N'ค่าล้างจาน', N'1', N'1', SUSER_SNAME(), GETDATE());

    SELECT @MenuId = menuId FROM dbo.Sysmenu WHERE menu_name_eng = @MenuKey;
    IF @MenuId IS NULL
    BEGIN
        INSERT INTO dbo.Sysmenu (
            menu_name_eng, MenuNameThai, MenuUrl, MenuImage, ParentMenu,
            OrderNo, TargetPage, IsActive, last_modified_date, last_modified_by
        )
        VALUES (
            @MenuKey, N'ค่าล้างจาน', @CmsBaseUrl + N'/dishwash/', @IconUrl, @RootMenuId,
            9, N'_self', 1, GETDATE(), SUSER_SNAME()
        );
        SET @MenuId = CONVERT(int, SCOPE_IDENTITY());
    END
    ELSE
        UPDATE dbo.Sysmenu
        SET MenuNameThai = N'ค่าล้างจาน', MenuUrl = @CmsBaseUrl + N'/dishwash/', MenuImage = @IconUrl,
            ParentMenu = @RootMenuId, OrderNo = 9, TargetPage = N'_self', IsActive = 1,
            last_modified_date = GETDATE(), last_modified_by = SUSER_SNAME()
        WHERE menuId = @MenuId;

    DECLARE @Grants table (GroupId uniqueidentifier NOT NULL, MenuId int NOT NULL, PRIMARY KEY (GroupId, MenuId));
    INSERT INTO @Grants (GroupId, MenuId)
    SELECT GroupId, @RootMenuId FROM @Groups
    UNION SELECT GroupId, @MenuId FROM @Groups;

    UPDATE existing SET existing.IsActive = 1
    FROM dbo.SysMenuGroupAssociate existing
    INNER JOIN @Grants g ON g.GroupId = existing.GroupId AND g.MenuId = existing.MenuId
    WHERE existing.IsActive <> 1;

    INSERT INTO dbo.SysMenuGroupAssociate (GroupId, MenuId, IsActive, CreateBy, CreateDate)
    SELECT g.GroupId, g.MenuId, 1, SUSER_SNAME(), GETDATE()
    FROM @Grants g
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.SysMenuGroupAssociate existing
        WHERE existing.GroupId = g.GroupId AND existing.MenuId = g.MenuId
    );

    -- คำอธิบายตาราง/คอลัมน์ (MS_Description) รันซ้ำได้: มีแล้วแก้ ไม่มีเพิ่ม
    DECLARE @Desc table (Col sysname NULL, Txt nvarchar(500) NOT NULL);
    INSERT INTO @Desc (Col, Txt) VALUES
        (NULL, N'ค่าล้างจานรายเดือนต่อสัญญา บันทึกจากเมนูค่าล้างจานใน CMS (1 แถวต่อสัญญาต่อรอบบิล)'),
        (N'Dishwash_id', N'รหัสรายการ (Identity)'),
        (N'Contract_id', N'รหัสสัญญา อ้าง Contract_hrd_tr.Contract_id'),
        (N'Contract_code', N'รหัสสัญญา ณ ตอนบันทึก (snapshot ไว้แสดงผล)'),
        (N'Billing_year_be', N'ปีของรอบบิล (พ.ศ.)'),
        (N'Billing_month', N'เดือนของรอบบิล 1-12'),
        (N'Amount', N'ยอดค่าล้างจาน (บาท) ผู้ใช้กรอกเอง'),
        (N'Remark', N'หมายเหตุ'),
        (N'Contract_debt_to_SAP', N'สถานะตั้งหนี้ SAP 0 = ยังไม่ตั้งหนี้, 1 = ตั้งหนี้แล้ว'),
        (N'Contract_fi_doc', N'เลขที่เอกสารตั้งหนี้ SAP ว่าง = ยังไม่ตั้งหนี้ (มีค่าแล้ว CMS ไม่ให้แก้ยอด)'),
        (N'Contract_fi_date', N'วันที่ตั้งหนี้ SAP'),
        (N'contract_paid_id', N'รหัสการชำระเงิน อ้าง Contract_paid_hd_tr'),
        (N'Contract_receipt_number', N'เลขที่ใบเสร็จ'),
        (N'Contract_receipt_date', N'วันที่ออกใบเสร็จ'),
        (N'UserEntry', N'ผู้บันทึก (Buasri ID)'),
        (N'DateEntry', N'วันเวลาที่บันทึก'),
        (N'UserUpdate', N'ผู้แก้ไขล่าสุด (Buasri ID)'),
        (N'DateUpdate', N'วันเวลาที่แก้ไขล่าสุด');

    DECLARE @Col sysname, @Txt nvarchar(500), @Level2Type varchar(10);
    DECLARE desc_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT Col, Txt FROM @Desc;
    OPEN desc_cursor;
    FETCH NEXT FROM desc_cursor INTO @Col, @Txt;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @Level2Type = CASE WHEN @Col IS NULL THEN NULL ELSE 'COLUMN' END;
        IF EXISTS (
            SELECT 1 FROM sys.extended_properties ep
            WHERE ep.major_id = OBJECT_ID(N'dbo.Contract_dishwash_tr') AND ep.name = N'MS_Description'
              AND ep.minor_id = ISNULL(COLUMNPROPERTY(OBJECT_ID(N'dbo.Contract_dishwash_tr'), @Col, 'ColumnId'), 0)
        )
            EXEC sys.sp_updateextendedproperty @name = N'MS_Description', @value = @Txt,
                @level0type = N'SCHEMA', @level0name = N'dbo',
                @level1type = N'TABLE', @level1name = N'Contract_dishwash_tr',
                @level2type = @Level2Type, @level2name = @Col;
        ELSE
            EXEC sys.sp_addextendedproperty @name = N'MS_Description', @value = @Txt,
                @level0type = N'SCHEMA', @level0name = N'dbo',
                @level1type = N'TABLE', @level1name = N'Contract_dishwash_tr',
                @level2type = @Level2Type, @level2name = @Col;
        FETCH NEXT FROM desc_cursor INTO @Col, @Txt;
    END;
    CLOSE desc_cursor;
    DEALLOCATE desc_cursor;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT m.menuId, m.menu_name_eng, m.MenuNameThai, m.OrderNo, s.GroupName, a.IsActive AS GroupAccessActive
FROM dbo.Sysmenu m
LEFT JOIN dbo.SysMenuGroupAssociate a ON a.MenuId = m.menuId
LEFT JOIN dbo.SysGroup s ON s.GroupId = a.GroupId
WHERE m.menuId = @MenuId
ORDER BY s.GroupName;
SELECT Contract_type_price_id, Contract_type_price_desc FROM dbo.Contract_type_price_ms
WHERE Contract_type_price_id = N'11';
