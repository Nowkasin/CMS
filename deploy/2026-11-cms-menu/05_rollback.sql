USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @RootMenuId int;

SELECT @RootMenuId = menuId
FROM dbo.Sysmenu
WHERE menu_name_eng = @RootKey;

IF @RootMenuId IS NULL
    THROW 50001, N'ไม่พบเมนูหลัก water_electric_new', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.SysMenuGroupAssociate
    SET IsActive = 0
    WHERE MenuId = @RootMenuId
       OR MenuId IN (
            SELECT menuId
            FROM dbo.Sysmenu
            WHERE ParentMenu = @RootMenuId
       );

    UPDATE dbo.Sysmenu
    SET
        IsActive           = 0,
        last_modified_date = GETDATE(),
        last_modified_by   = SUSER_SNAME()
    WHERE menuId = @RootMenuId
       OR ParentMenu = @RootMenuId;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT
    menuId,
    menu_name_eng,
    MenuNameThai,
    MenuUrl,
    ParentMenu,
    OrderNo,
    TargetPage,
    IsActive
FROM dbo.Sysmenu
WHERE menuId = @RootMenuId
   OR ParentMenu = @RootMenuId
ORDER BY ParentMenu, OrderNo, menuId;


