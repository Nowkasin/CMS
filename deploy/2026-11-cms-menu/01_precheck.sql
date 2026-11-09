USE [SWU_contract];
SET NOCOUNT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';

IF OBJECT_ID(N'dbo.Sysmenu', N'U') IS NULL
    THROW 50001, N'ไม่พบตาราง dbo.Sysmenu', 1;

IF OBJECT_ID(N'dbo.SysMenuGroupAssociate', N'U') IS NULL
    THROW 50002, N'ไม่พบตาราง dbo.SysMenuGroupAssociate', 1;

IF OBJECT_ID(N'dbo.SysGroup', N'U') IS NULL
    THROW 50003, N'ไม่พบตาราง dbo.SysGroup', 1;

IF EXISTS (
    SELECT menu_name_eng
    FROM dbo.Sysmenu
    WHERE menu_name_eng IN (
        @RootKey,
        N'meter_management',
        N'excel_upload',
        N'excel_download',
        N'phase_management',
        N'dashboard_view',
        N'contract_termination',
        N'activity_log_view'
    )
    GROUP BY menu_name_eng
    HAVING COUNT(*) > 1
)
    THROW 50005, N'พบ menu_name_eng ซ้ำ ต้องแก้ข้อมูลซ้ำก่อนติดตั้ง', 1;

SELECT
    DB_NAME() AS DatabaseName,
    @@SERVERNAME AS ServerName,
    SUSER_SNAME() AS LoginName,
    IS_SRVROLEMEMBER(N'sysadmin') AS IsSysAdmin;

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
WHERE menuId = 41
   OR menu_name_eng IN (
        @RootKey,
        N'meter_management',
        N'excel_upload',
        N'excel_download',
        N'phase_management',
        N'dashboard_view',
        N'contract_termination',
        N'activity_log_view'
   )
ORDER BY ParentMenu, OrderNo, menuId;

SELECT
    GroupId,
    GroupName,
    IsActive
FROM dbo.SysGroup
ORDER BY GroupName;

SELECT
    association.GroupId,
    groups.GroupName,
    association.MenuId,
    menu.menu_name_eng,
    menu.MenuNameThai,
    association.IsActive
FROM dbo.SysMenuGroupAssociate AS association
INNER JOIN dbo.SysGroup AS groups
    ON groups.GroupId = association.GroupId
INNER JOIN dbo.Sysmenu AS menu
    ON menu.menuId = association.MenuId
WHERE menu.menuId = 41
   OR menu.menu_name_eng IN (
        @RootKey,
        N'meter_management',
        N'excel_upload',
        N'excel_download',
        N'phase_management',
        N'dashboard_view',
        N'contract_termination',
        N'activity_log_view'
   )
ORDER BY groups.GroupName, menu.OrderNo, menu.menuId;

