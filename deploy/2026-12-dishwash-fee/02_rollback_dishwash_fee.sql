-- ย้อน 01_apply_dishwash_fee.sql
--   ปิดเมนู dishwash_fee และสิทธิ์ของเมนูนี้ (IsActive = 0 ไม่ลบแถว) ไม่แตะเมนูหลัก
--   ลบตาราง Contract_dishwash_tr เฉพาะเมื่อยังไม่มีข้อมูล (มีข้อมูล = หยุด ให้ตัดสินใจเองก่อน)
--   ลบประเภท 11 เฉพาะเมื่อไม่มีตารางใดอ้างอิง
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.Contract_dishwash_tr', N'U') IS NOT NULL
BEGIN
    DECLARE @Rows int;
    EXEC sys.sp_executesql N'SELECT @n = COUNT(*) FROM dbo.Contract_dishwash_tr', N'@n int OUTPUT', @n = @Rows OUTPUT;
    IF @Rows > 0
        THROW 50020, N'Contract_dishwash_tr มีข้อมูลอยู่ -- Export/ลบข้อมูลเองก่อนถ้าต้องการย้อนจริง', 1;
END;

BEGIN TRANSACTION;

UPDATE a SET a.IsActive = 0
FROM dbo.SysMenuGroupAssociate a
INNER JOIN dbo.Sysmenu m ON m.menuId = a.MenuId
WHERE m.menu_name_eng = N'dishwash_fee' AND a.IsActive = 1;

UPDATE dbo.Sysmenu SET IsActive = 0, last_modified_date = GETDATE(), last_modified_by = SUSER_SNAME()
WHERE menu_name_eng = N'dishwash_fee' AND IsActive = 1;

IF OBJECT_ID(N'dbo.Contract_dishwash_tr', N'U') IS NOT NULL
    EXEC sys.sp_executesql N'DROP TABLE dbo.Contract_dishwash_tr';

IF NOT EXISTS (SELECT 1 FROM dbo.Contract_price_tr WHERE CAST(Contract_type_price_id AS nvarchar(20)) = N'11')
   AND NOT EXISTS (SELECT 1 FROM dbo.Contract_Installment_tr WHERE CAST(Contract_type_price_id AS nvarchar(20)) = N'11')
    DELETE FROM dbo.Contract_type_price_ms
    WHERE Contract_type_price_id = N'11' AND Contract_type_price_desc = N'ค่าล้างจาน';

COMMIT TRANSACTION;
SELECT N'rolled back' AS Result;
