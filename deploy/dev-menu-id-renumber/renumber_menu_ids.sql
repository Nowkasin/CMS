USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

-- PREVIEW = แสดง mapping เท่านั้น, APPLY = ย้ายเลข, ROLLBACK = คืนเลขเดิม
DECLARE @Mode nvarchar(10) = N'PREVIEW';
DECLARE @IdentityInsertOn bit = 0;
DECLARE @LockCount bigint;

IF @Mode NOT IN (N'PREVIEW', N'APPLY', N'ROLLBACK')
    THROW 51001, N'@Mode ต้องเป็น PREVIEW, APPLY หรือ ROLLBACK', 1;

DECLARE @Map table (
    OldMenuId int NOT NULL PRIMARY KEY,
    NewMenuId int NOT NULL UNIQUE,
    MenuKey nvarchar(100) NOT NULL UNIQUE,
    NewParentMenu int NOT NULL,
    NewOrderNo int NOT NULL
);

IF @Mode IN (N'PREVIEW', N'APPLY')
BEGIN
    INSERT INTO @Map (
        OldMenuId,
        NewMenuId,
        MenuKey,
        NewParentMenu,
        NewOrderNo
    )
    VALUES
        (90, 83, N'water_electric_new', 0, 9),
        (83, 84, N'meter_management', 83, 1),
        (84, 85, N'excel_upload', 83, 2),
        (85, 86, N'excel_download', 83, 3),
        (86, 87, N'phase_management', 83, 4),
        (87, 88, N'dashboard_view', 83, 5),
        (88, 89, N'contract_termination', 83, 6),
        (89, 90, N'activity_log_view', 83, 7);
END
ELSE
BEGIN
    INSERT INTO @Map (
        OldMenuId,
        NewMenuId,
        MenuKey,
        NewParentMenu,
        NewOrderNo
    )
    VALUES
        (83, 90, N'water_electric_new', 0, 9),
        (84, 83, N'meter_management', 90, 1),
        (85, 84, N'excel_upload', 90, 2),
        (86, 85, N'excel_download', 90, 3),
        (87, 86, N'phase_management', 90, 4),
        (88, 87, N'dashboard_view', 90, 5),
        (89, 88, N'contract_termination', 90, 6),
        (90, 89, N'activity_log_view', 90, 7);
END;

SELECT
    @Mode AS Mode,
    mapping.OldMenuId,
    mapping.NewMenuId,
    mapping.MenuKey,
    current_menu.MenuNameThai,
    current_menu.ParentMenu AS CurrentParentMenu,
    mapping.NewParentMenu,
    current_menu.OrderNo AS CurrentOrderNo,
    mapping.NewOrderNo
FROM @Map AS mapping
LEFT JOIN dbo.Sysmenu AS current_menu
    ON current_menu.menuId = mapping.OldMenuId
   AND current_menu.menu_name_eng = mapping.MenuKey
ORDER BY mapping.NewMenuId;

IF @Mode = N'PREVIEW'
    RETURN;

DECLARE @Menus table (
    OldMenuId int NOT NULL PRIMARY KEY,
    NewMenuId int NOT NULL,
    menu_name_eng nvarchar(max) NULL,
    MenuNameThai nvarchar(max) NULL,
    MenuUrl nvarchar(max) NULL,
    MenuImage nvarchar(max) NULL,
    TargetPage nvarchar(max) NULL,
    IsActive bit NULL
);

DECLARE @Associations table (
    GroupId uniqueidentifier NOT NULL,
    NewMenuId int NOT NULL,
    IsActive bit NULL,
    CreateBy nvarchar(max) NULL,
    CreateDate datetime NULL
);

DECLARE @TempAssociations table (
    TempId uniqueidentifier NOT NULL,
    GroupId uniqueidentifier NOT NULL,
    NewMenuId int NOT NULL,
    IsActive bit NULL
);

BEGIN TRY
    BEGIN TRANSACTION;

    -- ป้องกัน K2 เขียนตารางเมนูหรือสิทธิ์แทรกระหว่างการย้าย
    SELECT @LockCount = COUNT_BIG(*)
    FROM dbo.Sysmenu WITH (TABLOCKX, HOLDLOCK);

    SELECT @LockCount = COUNT_BIG(*)
    FROM dbo.SysMenuGroupAssociate WITH (TABLOCKX, HOLDLOCK);

    SELECT @LockCount = COUNT_BIG(*)
    FROM dbo.Temp_SysMenuGroupAssociate WITH (TABLOCKX, HOLDLOCK);

    IF (
        SELECT COUNT(*)
        FROM @Map AS mapping
        INNER JOIN dbo.Sysmenu AS menu
            ON menu.menuId = mapping.OldMenuId
           AND menu.menu_name_eng = mapping.MenuKey
    ) <> 8
        THROW 51002, N'เลข menuId และ menu_name_eng ไม่ตรงกับ mapping ที่คาดไว้', 1;

    IF EXISTS (
        SELECT 1
        FROM dbo.Sysmenu AS menu
        WHERE menu.ParentMenu IN (SELECT OldMenuId FROM @Map)
          AND menu.menuId NOT IN (SELECT OldMenuId FROM @Map)
    )
        THROW 51003, N'พบเมนูอื่นอ้าง ParentMenu ในช่วงที่จะย้าย', 1;

    INSERT INTO @Menus (
        OldMenuId,
        NewMenuId,
        menu_name_eng,
        MenuNameThai,
        MenuUrl,
        MenuImage,
        TargetPage,
        IsActive
    )
    SELECT
        mapping.OldMenuId,
        mapping.NewMenuId,
        menu.menu_name_eng,
        menu.MenuNameThai,
        menu.MenuUrl,
        menu.MenuImage,
        menu.TargetPage,
        menu.IsActive
    FROM @Map AS mapping
    INNER JOIN dbo.Sysmenu AS menu
        ON menu.menuId = mapping.OldMenuId;

    INSERT INTO @Associations (
        GroupId,
        NewMenuId,
        IsActive,
        CreateBy,
        CreateDate
    )
    SELECT
        association.GroupId,
        mapping.NewMenuId,
        association.IsActive,
        association.CreateBy,
        association.CreateDate
    FROM dbo.SysMenuGroupAssociate AS association
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = association.MenuId;

    INSERT INTO @TempAssociations (
        TempId,
        GroupId,
        NewMenuId,
        IsActive
    )
    SELECT
        association.TempId,
        association.GroupId,
        mapping.NewMenuId,
        association.IsActive
    FROM dbo.Temp_SysMenuGroupAssociate AS association
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = association.MenuId;

    DELETE association
    FROM dbo.Temp_SysMenuGroupAssociate AS association
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = association.MenuId;

    DELETE association
    FROM dbo.SysMenuGroupAssociate AS association
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = association.MenuId;

    DELETE menu
    FROM dbo.Sysmenu AS menu
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = menu.menuId;

    SET IDENTITY_INSERT dbo.Sysmenu ON;
    SET @IdentityInsertOn = 1;

    INSERT INTO dbo.Sysmenu (
        menuId,
        menu_name_eng,
        MenuNameThai,
        MenuUrl,
        MenuImage,
        ParentMenu,
        OrderNo,
        TargetPage,
        IsActive,
        last_modified_date,
        last_modified_by
    )
    SELECT
        menu.NewMenuId,
        menu.menu_name_eng,
        menu.MenuNameThai,
        menu.MenuUrl,
        menu.MenuImage,
        mapping.NewParentMenu,
        mapping.NewOrderNo,
        menu.TargetPage,
        menu.IsActive,
        GETDATE(),
        SUSER_SNAME()
    FROM @Menus AS menu
    INNER JOIN @Map AS mapping
        ON mapping.OldMenuId = menu.OldMenuId;

    SET IDENTITY_INSERT dbo.Sysmenu OFF;
    SET @IdentityInsertOn = 0;

    INSERT INTO dbo.SysMenuGroupAssociate (
        GroupId,
        MenuId,
        IsActive,
        CreateBy,
        CreateDate
    )
    SELECT
        GroupId,
        NewMenuId,
        IsActive,
        CreateBy,
        CreateDate
    FROM @Associations;

    INSERT INTO dbo.Temp_SysMenuGroupAssociate (
        TempId,
        GroupId,
        MenuId,
        IsActive
    )
    SELECT
        TempId,
        GroupId,
        NewMenuId,
        IsActive
    FROM @TempAssociations;

    IF (
        SELECT COUNT(*)
        FROM @Map AS mapping
        INNER JOIN dbo.Sysmenu AS menu
            ON menu.menuId = mapping.NewMenuId
           AND menu.menu_name_eng = mapping.MenuKey
           AND menu.ParentMenu = mapping.NewParentMenu
           AND menu.OrderNo = mapping.NewOrderNo
    ) <> 8
        THROW 51004, N'ผลตรวจหลังย้ายเมนูไม่ครบ 8 รายการ', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    IF @IdentityInsertOn = 1
        SET IDENTITY_INSERT dbo.Sysmenu OFF;

    THROW;
END CATCH;

SELECT
    menu.menuId,
    menu.menu_name_eng,
    menu.MenuNameThai,
    menu.ParentMenu,
    menu.OrderNo,
    menu.IsActive
FROM dbo.Sysmenu AS menu
WHERE menu.menu_name_eng IN (
    N'water_electric_new',
    N'meter_management',
    N'excel_upload',
    N'excel_download',
    N'phase_management',
    N'dashboard_view',
    N'contract_termination',
    N'activity_log_view'
)
ORDER BY menu.menuId;

