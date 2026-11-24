-- เพิ่มเมนู "ใบแจ้งหนี้" (key invoice_print) เป็นเมนูย่อยของระบบ water_electric_new
-- และให้สิทธิ์กลุ่มส่วนการคลัง -- รันภายใน Transaction เดียว ไม่แก้ Schema
-- ผู้ดูแลฐานข้อมูลเป็นผู้รัน (โค้ด Django ไม่เขียนตารางเมนู/สิทธิ์เอง)
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

-- ต้องแก้เป็น URL จริงก่อนรัน ให้ตรงกับที่ใช้ใน deploy/2026-11-cms-menu/02_apply_menu.sql
DECLARE @CmsBaseUrl nvarchar(500) = N'https://CHANGE-ME.example/cms';
DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @MenuKey nvarchar(100) = N'invoice_print';
DECLARE @IconUrl nvarchar(500) =
    N'/Runtime/Styles/Themes/Platinum/ico-quotation-request.png';
-- กลุ่มที่เห็นเมนู (ตรวจจาก SysGroup แล้ว) -- เพิ่มกลุ่มอื่นในตารางนี้ได้
--   5C8F2016-... = Cashier ID Approve ส่วนการคลัง (ผู้ใช้งานหลัก)
--   9B148353-... = ผู้ดูแลระบบ ( Admin ) (ดูแล/ทดสอบเมนู)
DECLARE @Groups table (GroupId uniqueidentifier NOT NULL PRIMARY KEY);
INSERT INTO @Groups (GroupId) VALUES
    ('5C8F2016-ED3C-4E31-8633-CD8984FD7DCB'),
    ('9B148353-6383-40D7-B3B8-F04FC8C5A4C5');

DECLARE @RootMenuId int;
DECLARE @MenuId int;

IF @CmsBaseUrl LIKE N'%CHANGE-ME%'
    THROW 50001, N'กรุณากำหนด @CmsBaseUrl เป็น URL จริงก่อนรัน', 1;

WHILE RIGHT(@CmsBaseUrl, 1) = N'/'
    SET @CmsBaseUrl = LEFT(@CmsBaseUrl, LEN(@CmsBaseUrl) - 1);

SELECT @RootMenuId = menuId FROM dbo.Sysmenu WHERE menu_name_eng = @RootKey AND IsActive = 1;
IF @RootMenuId IS NULL
    THROW 50002, N'ไม่พบเมนูหลัก water_electric_new -- ต้องติดตั้ง deploy/2026-11-cms-menu ก่อน', 1;

IF EXISTS (
    SELECT 1 FROM @Groups g LEFT JOIN dbo.SysGroup s ON s.GroupId = g.GroupId
    WHERE s.GroupId IS NULL OR ISNULL(s.IsActive, 0) <> 1
)
    THROW 50003, N'พบ GroupId ที่ไม่มีอยู่หรือไม่ได้เปิดใช้งาน', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    SELECT @MenuId = menuId FROM dbo.Sysmenu WHERE menu_name_eng = @MenuKey;

    IF @MenuId IS NULL
    BEGIN
        INSERT INTO dbo.Sysmenu (
            menu_name_eng, MenuNameThai, MenuUrl, MenuImage, ParentMenu,
            OrderNo, TargetPage, IsActive, last_modified_date, last_modified_by
        )
        VALUES (
            @MenuKey, N'ใบแจ้งหนี้', @CmsBaseUrl + N'/invoice/', @IconUrl, @RootMenuId,
            8, N'_self', 1, GETDATE(), SUSER_SNAME()
        );
        SET @MenuId = CONVERT(int, SCOPE_IDENTITY());
    END
    ELSE
    BEGIN
        UPDATE dbo.Sysmenu
        SET MenuNameThai = N'ใบแจ้งหนี้', MenuUrl = @CmsBaseUrl + N'/invoice/', MenuImage = @IconUrl,
            ParentMenu = @RootMenuId, OrderNo = 8, TargetPage = N'_self', IsActive = 1,
            last_modified_date = GETDATE(), last_modified_by = SUSER_SNAME()
        WHERE menuId = @MenuId;
    END;

    -- กลุ่มที่ใช้เมนูย่อยต้องมีสิทธิ์เมนูหลักด้วย (CMS ตรวจผ่าน water_electric_new)
    DECLARE @Grants table (GroupId uniqueidentifier NOT NULL, MenuId int NOT NULL, PRIMARY KEY (GroupId, MenuId));
    INSERT INTO @Grants (GroupId, MenuId)
    SELECT GroupId, @RootMenuId FROM @Groups
    UNION SELECT GroupId, @MenuId FROM @Groups;

    UPDATE existing SET existing.IsActive = 1
    FROM dbo.SysMenuGroupAssociate existing
    INNER JOIN @Grants g ON g.GroupId = existing.GroupId AND g.MenuId = existing.MenuId;

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

SELECT m.menuId, m.menu_name_eng, m.MenuNameThai, m.MenuUrl, m.ParentMenu, m.OrderNo, m.IsActive,
       s.GroupName, a.IsActive AS GroupAccessActive
FROM dbo.Sysmenu m
LEFT JOIN dbo.SysMenuGroupAssociate a ON a.MenuId = m.menuId
LEFT JOIN dbo.SysGroup s ON s.GroupId = a.GroupId
WHERE m.menuId IN (@RootMenuId, @MenuId)
  AND (a.GroupId IS NULL OR a.GroupId IN (SELECT GroupId FROM @Groups))
ORDER BY m.ParentMenu, m.OrderNo;
