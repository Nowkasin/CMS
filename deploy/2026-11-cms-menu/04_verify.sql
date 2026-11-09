USE [SWU_contract];
SET NOCOUNT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @RootMenuId int;

SELECT @RootMenuId = menuId
FROM dbo.Sysmenu
WHERE menu_name_eng = @RootKey
  AND IsActive = 1;

IF @RootMenuId IS NULL
    THROW 50001, N'ไม่พบเมนูหลัก water_electric_new ที่เปิดใช้งาน', 1;

IF (
    SELECT COUNT(*)
    FROM dbo.Sysmenu
    WHERE ParentMenu = @RootMenuId
      AND IsActive = 1
      AND menu_name_eng IN (
          N'meter_management',
          N'excel_upload',
          N'excel_download',
          N'phase_management',
          N'dashboard_view',
          N'contract_termination',
          N'activity_log_view'
      )
) <> 7
    THROW 50002, N'เมนูย่อยที่เปิดใช้งานใต้ระบบใหม่ไม่ครบ 7 รายการ', 1;

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

SELECT
    groups.GroupId,
    groups.GroupName,
    menu.menuId,
    menu.menu_name_eng,
    menu.MenuNameThai,
    association.IsActive AS PermissionIsActive
FROM dbo.SysMenuGroupAssociate AS association
INNER JOIN dbo.SysGroup AS groups
    ON groups.GroupId = association.GroupId
INNER JOIN dbo.Sysmenu AS menu
    ON menu.menuId = association.MenuId
WHERE menu.menuId = @RootMenuId
   OR menu.ParentMenu = @RootMenuId
ORDER BY groups.GroupName, menu.OrderNo, menu.menuId;

-- กลุ่มที่มีสิทธิ์เมนูย่อย แต่ไม่มีสิทธิ์เมนูหลัก จะเข้า CMS ไม่ได้
SELECT DISTINCT
    child_permission.GroupId,
    groups.GroupName
FROM dbo.SysMenuGroupAssociate AS child_permission
INNER JOIN dbo.SysGroup AS groups
    ON groups.GroupId = child_permission.GroupId
INNER JOIN dbo.Sysmenu AS child_menu
    ON child_menu.menuId = child_permission.MenuId
WHERE child_menu.ParentMenu = @RootMenuId
  AND child_permission.IsActive = 1
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.SysMenuGroupAssociate AS root_permission
      WHERE root_permission.GroupId = child_permission.GroupId
        AND root_permission.MenuId = @RootMenuId
        AND root_permission.IsActive = 1
  );


