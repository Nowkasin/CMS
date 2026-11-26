-- ตรวจฐานข้อมูลและ URL ก่อนรัน สคริปต์นี้ไม่ได้ให้สิทธิ์กลุ่มใดอัตโนมัติ
-- ParentMenu อยู่ใต้ CMS ตามรูปแบบอ่านสิทธิ์เดิม ส่วน Sidebar จัดกลุ่มใต้แดชบอร์ด
USE [SWU_contract];
SET XACT_ABORT ON;
DECLARE @Mode nvarchar(10) = N'PREVIEW'; -- เปลี่ยนเป็น APPLY เมื่อตรวจแล้ว
DECLARE @MenuUrl nvarchar(1000) = N''; -- URL เต็มที่ใช้งานจริง เช่น https://host/cms/dashboard/spaces/
IF @Mode NOT IN (N'PREVIEW', N'APPLY')
    THROW 50001, N'Mode ต้องเป็น PREVIEW หรือ APPLY', 1;
IF (SELECT COUNT(*) FROM dbo.Sysmenu WHERE menu_name_eng = N'water_electric_new' AND IsActive = 1) <> 1
    THROW 50002, N'ไม่พบเมนูหลัก CMS ที่เปิดใช้งานเพียงรายการเดียว', 1;
DECLARE @ParentId int = (SELECT menuId FROM dbo.Sysmenu WHERE menu_name_eng = N'water_electric_new' AND IsActive = 1);
IF @Mode = N'PREVIEW'
BEGIN
    SELECT @ParentId AS ParentMenu, N'space_dashboard_view' AS menu_name_eng,
           N'ภาพรวมพื้นที่เช่า' AS MenuNameThai, @MenuUrl AS MenuUrl;
    SELECT * FROM dbo.Sysmenu WHERE menu_name_eng = N'space_dashboard_view';
    RETURN;
END;
IF NULLIF(LTRIM(RTRIM(@MenuUrl)), N'') IS NULL
    THROW 50003, N'กรอก MenuUrl จริงก่อน APPLY', 1;
BEGIN TRY
    BEGIN TRANSACTION;
    IF EXISTS (SELECT 1 FROM dbo.Sysmenu WITH (UPDLOCK, HOLDLOCK) WHERE menu_name_eng = N'space_dashboard_view')
        THROW 50004, N'มีเมนูนี้แล้ว ตรวจรายการเดิมก่อน ไม่สร้างซ้ำ', 1;
    INSERT dbo.Sysmenu (menu_name_eng, MenuNameThai, MenuUrl, MenuImage,
        ParentMenu, OrderNo, TargetPage, IsActive, last_modified_date, last_modified_by)
    VALUES (N'space_dashboard_view', N'ภาพรวมพื้นที่เช่า', @MenuUrl,
        N'/Runtime/Styles/Themes/Platinum/ico-quotation-request.png',
        @ParentId, 11, N'_self', 1, GETDATE(), SUSER_SNAME());
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
SELECT menuId, menu_name_eng, MenuNameThai, MenuUrl, ParentMenu
FROM dbo.Sysmenu WHERE menu_name_eng = N'space_dashboard_view';
