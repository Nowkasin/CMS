-- ให้สิทธิ์เมนู "ประวัติการใช้งาน" (key activity_log_view) กับกลุ่มทดสอบ 2 กลุ่ม
-- คนที่ไม่ใช่ผู้ดูแลระบบจะเห็น log เฉพาะเหตุการณ์ของเมนูที่กลุ่มตัวเองมีสิทธิ์ (กรองในโค้ด
-- meters/views/activity_log.py ตาม ACTION_PERMISSIONS ใน meters/services/activity_log.py)
-- เพิ่มสิทธิ์อย่างเดียว ไม่ปิดสิทธิ์ของกลุ่มอื่น (Admin มีอยู่แล้ว) ไม่แก้ Sysmenu ไม่แก้ Schema รันซ้ำได้
-- ผู้ดูแลฐานข้อมูลเป็นผู้รัน (โค้ด Django ไม่เขียนตารางเมนู/สิทธิ์เอง)
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @MenuKey nvarchar(100) = N'activity_log_view';
-- GroupId ตรวจจาก SysGroup บน DEV แล้ว -- ตรวจซ้ำบน PRD ก่อนรัน
--   00B67BB6-... = ทดสอบ หลังบ้านตั้งหนี้ CMS, SAP
--   31200B53-... = ทดสอบ หน้าบ้านสร้างสัญญา
DECLARE @Groups table (GroupId uniqueidentifier NOT NULL PRIMARY KEY);
INSERT INTO @Groups (GroupId) VALUES
    ('00B67BB6-1982-400F-BA50-33CF8FA36D3E'),
    ('31200B53-36EC-47A1-88F2-4463A597C0F9');

DECLARE @RootMenuId int;
DECLARE @MenuId int;

SELECT @RootMenuId = menuId FROM dbo.Sysmenu WHERE menu_name_eng = @RootKey AND IsActive = 1;
IF @RootMenuId IS NULL
    THROW 50002, N'ไม่พบเมนูหลัก water_electric_new -- ต้องติดตั้ง deploy/2026-11-cms-menu ก่อน', 1;

SELECT @MenuId = menuId FROM dbo.Sysmenu
WHERE menu_name_eng = @MenuKey AND ParentMenu = @RootMenuId AND IsActive = 1;
IF @MenuId IS NULL
    THROW 50004, N'ไม่พบเมนู activity_log_view ที่เปิดใช้งาน -- ต้องติดตั้ง deploy/2026-11-cms-menu ก่อน', 1;

IF EXISTS (
    SELECT 1 FROM @Groups g LEFT JOIN dbo.SysGroup s ON s.GroupId = g.GroupId
    WHERE s.GroupId IS NULL OR ISNULL(s.IsActive, 0) <> 1
)
    THROW 50003, N'พบ GroupId ที่ไม่มีอยู่หรือไม่ได้เปิดใช้งาน', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    -- กลุ่มต้องมีสิทธิ์เมนูหลักด้วย (ปกติมีอยู่แล้วจากเมนูใบแจ้งหนี้)
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

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT m.menu_name_eng, s.GroupName, a.IsActive AS GroupAccessActive, a.CreateDate
FROM dbo.SysMenuGroupAssociate a
INNER JOIN dbo.Sysmenu m ON m.menuId = a.MenuId
INNER JOIN dbo.SysGroup s ON s.GroupId = a.GroupId
WHERE m.menuId = @MenuId
ORDER BY a.IsActive DESC, s.GroupName;
