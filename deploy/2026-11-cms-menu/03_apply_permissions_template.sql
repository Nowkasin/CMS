USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @RootKey nvarchar(100) = N'water_electric_new';

DECLARE @Permissions table (
    GroupId uniqueidentifier NOT NULL,
    MenuKey nvarchar(100) NOT NULL,
    PRIMARY KEY (GroupId, MenuKey)
);

-- เพิ่มสิทธิ์ที่ต้องการก่อนรัน ตัวอย่าง:
-- INSERT INTO @Permissions (GroupId, MenuKey) VALUES
--     ('00000000-0000-0000-0000-000000000000', N'water_electric_new'),
--     ('00000000-0000-0000-0000-000000000000', N'meter_management');

IF NOT EXISTS (SELECT 1 FROM @Permissions)
    THROW 50001, N'ยังไม่ได้กำหนดรายการใน @Permissions', 1;

IF EXISTS (
    SELECT 1
    FROM @Permissions AS requested
    WHERE requested.MenuKey IN (
          N'meter_management',
          N'excel_upload',
          N'excel_download',
          N'phase_management',
          N'dashboard_view',
          N'contract_termination',
          N'activity_log_view'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM @Permissions AS root_permission
          WHERE root_permission.GroupId = requested.GroupId
            AND root_permission.MenuKey = @RootKey
      )
)
    THROW 50002, N'ทุกกลุ่มที่ใช้เมนูย่อยต้องได้รับสิทธิ์ water_electric_new', 1;

IF EXISTS (
    SELECT 1
    FROM @Permissions AS requested
    LEFT JOIN dbo.SysGroup AS groups
        ON groups.GroupId = requested.GroupId
    WHERE groups.GroupId IS NULL
       OR ISNULL(groups.IsActive, 0) <> 1
)
    THROW 50003, N'พบ GroupId ที่ไม่มีอยู่หรือไม่ได้เปิดใช้งาน', 1;

IF EXISTS (
    SELECT 1
    FROM @Permissions AS requested
    LEFT JOIN dbo.Sysmenu AS menu
        ON menu.menu_name_eng = requested.MenuKey
    WHERE menu.menuId IS NULL
       OR ISNULL(menu.IsActive, 0) <> 1
)
    THROW 50004, N'พบ MenuKey ที่ไม่มีอยู่หรือไม่ได้เปิดใช้งาน', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE existing
    SET existing.IsActive = 1
    FROM dbo.SysMenuGroupAssociate AS existing
    INNER JOIN dbo.Sysmenu AS menu
        ON menu.menuId = existing.MenuId
    INNER JOIN @Permissions AS requested
        ON requested.GroupId = existing.GroupId
       AND requested.MenuKey = menu.menu_name_eng;

    INSERT INTO dbo.SysMenuGroupAssociate (
        GroupId,
        MenuId,
        IsActive,
        CreateBy,
        CreateDate
    )
    SELECT
        requested.GroupId,
        menu.menuId,
        1,
        SUSER_SNAME(),
        GETDATE()
    FROM @Permissions AS requested
    INNER JOIN dbo.Sysmenu AS menu
        ON menu.menu_name_eng = requested.MenuKey
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.SysMenuGroupAssociate AS existing
        WHERE existing.GroupId = requested.GroupId
          AND existing.MenuId = menu.menuId
    );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT
    groups.GroupId,
    groups.GroupName,
    menu.menuId,
    menu.menu_name_eng,
    menu.MenuNameThai,
    association.IsActive
FROM dbo.SysMenuGroupAssociate AS association
INNER JOIN dbo.SysGroup AS groups
    ON groups.GroupId = association.GroupId
INNER JOIN dbo.Sysmenu AS menu
    ON menu.menuId = association.MenuId
INNER JOIN @Permissions AS requested
    ON requested.GroupId = association.GroupId
   AND requested.MenuKey = menu.menu_name_eng
ORDER BY groups.GroupName, menu.OrderNo, menu.menuId;

