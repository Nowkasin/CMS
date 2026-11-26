-- ปิดเมนู "ใบแจ้งหนี้" (invoice_print) และสิทธิ์ของเมนูนี้ โดยไม่ลบแถว
-- ไม่แตะสิทธิ์เมนูหลัก water_electric_new ของกลุ่ม เพราะกลุ่มอาจใช้เมนูอื่นของระบบอยู่
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @MenuKey nvarchar(100) = N'invoice_print';

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE a SET a.IsActive = 0
    FROM dbo.SysMenuGroupAssociate a
    INNER JOIN dbo.Sysmenu m ON m.menuId = a.MenuId
    WHERE m.menu_name_eng = @MenuKey;

    UPDATE dbo.Sysmenu
    SET IsActive = 0, last_modified_date = GETDATE(), last_modified_by = SUSER_SNAME()
    WHERE menu_name_eng = @MenuKey;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT menuId, menu_name_eng, MenuNameThai, IsActive FROM dbo.Sysmenu WHERE menu_name_eng = @MenuKey;
