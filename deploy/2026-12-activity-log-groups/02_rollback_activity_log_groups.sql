-- ย้อน 01_apply_activity_log_groups.sql: ปิดสิทธิ์เมนู "ประวัติการใช้งาน" ของกลุ่มทดสอบ 2 กลุ่ม
-- ปิด (IsActive = 0) ไม่ลบแถว และไม่แตะสิทธิ์เมนูหลัก เพราะกลุ่มยังใช้เมนูใบแจ้งหนี้อยู่
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @MenuKey nvarchar(100) = N'activity_log_view';
DECLARE @Groups table (GroupId uniqueidentifier NOT NULL PRIMARY KEY);
INSERT INTO @Groups (GroupId) VALUES
    ('00B67BB6-1982-400F-BA50-33CF8FA36D3E'),
    ('31200B53-36EC-47A1-88F2-4463A597C0F9');

DECLARE @MenuId int;
SELECT @MenuId = m.menuId
FROM dbo.Sysmenu m
INNER JOIN dbo.Sysmenu root ON root.menuId = m.ParentMenu AND root.menu_name_eng = @RootKey
WHERE m.menu_name_eng = @MenuKey;
IF @MenuId IS NULL
    THROW 50004, N'ไม่พบเมนู activity_log_view', 1;

BEGIN TRANSACTION;
UPDATE a SET a.IsActive = 0
FROM dbo.SysMenuGroupAssociate a
WHERE a.MenuId = @MenuId
  AND a.IsActive = 1
  AND a.GroupId IN (SELECT GroupId FROM @Groups);
SELECT @@ROWCOUNT AS DisabledGrants;
COMMIT TRANSACTION;
