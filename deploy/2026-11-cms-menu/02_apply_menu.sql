USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

-- ต้องแก้เป็น URL จริงก่อนรัน เช่น https://example.swu.ac.th/cms
DECLARE @CmsBaseUrl nvarchar(500) = N'https://CHANGE-ME.example/cms';
DECLARE @RootKey nvarchar(100) = N'water_electric_new';
DECLARE @IconUrl nvarchar(500) =
    N'/Runtime/Styles/Themes/Platinum/ico-quotation-request.png';
DECLARE @RootMenuId int;
DECLARE @RootOrderNo int;

IF @CmsBaseUrl LIKE N'%CHANGE-ME%'
    THROW 50001, N'กรุณากำหนด @CmsBaseUrl เป็น URL จริงก่อนรัน', 1;

IF @CmsBaseUrl NOT LIKE N'https://%'
    THROW 50005, N'@CmsBaseUrl ของ PRD ต้องขึ้นต้นด้วย https://', 1;

WHILE RIGHT(@CmsBaseUrl, 1) = N'/'
    SET @CmsBaseUrl = LEFT(@CmsBaseUrl, LEN(@CmsBaseUrl) - 1);

DECLARE @Menus table (
    MenuKey nvarchar(100) NOT NULL PRIMARY KEY,
    ThaiName nvarchar(200) NOT NULL,
    RelativePath nvarchar(200) NOT NULL,
    OrderNo int NOT NULL
);

INSERT INTO @Menus (MenuKey, ThaiName, RelativePath, OrderNo)
VALUES
    (N'meter_management', N'จัดการมิเตอร์', N'/meters/', 1),
    (N'excel_upload', N'อัปโหลดไฟล์', N'/upload/', 2),
    (N'excel_download', N'ดาวน์โหลด Excel', N'/download/', 3),
    (N'phase_management', N'จัดการระบบไฟฟ้า', N'/phases/', 4),
    (N'dashboard_view', N'แดชบอร์ด', N'/dashboard/', 5),
    (N'contract_termination', N'ยกเลิกสัญญา', N'/termination/', 6),
    (N'activity_log_view', N'ประวัติการใช้งาน', N'/log/', 7);

BEGIN TRY
    BEGIN TRANSACTION;

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
        THROW 50003, N'พบ menu_name_eng ซ้ำ จึงยกเลิกการติดตั้ง', 1;

    SELECT @RootMenuId = menuId
    FROM dbo.Sysmenu
    WHERE menu_name_eng = @RootKey;

    SELECT @RootOrderNo = ISNULL(MAX(OrderNo), 0) + 1
    FROM dbo.Sysmenu
    WHERE ISNULL(ParentMenu, 0) = 0;

    IF @RootMenuId IS NULL
    BEGIN
        INSERT INTO dbo.Sysmenu (
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
        VALUES (
            @RootKey,
            N'ค่าน้ำประปา-ค่าไฟฟ้า',
            @CmsBaseUrl + N'/login/',
            @IconUrl,
            0,
            @RootOrderNo,
            N'_blank',
            1,
            GETDATE(),
            SUSER_SNAME()
        );

        SET @RootMenuId = CONVERT(int, SCOPE_IDENTITY());
    END
    ELSE
    BEGIN
        UPDATE dbo.Sysmenu
        SET
            MenuNameThai       = N'ค่าน้ำประปา-ค่าไฟฟ้า',
            MenuUrl            = @CmsBaseUrl + N'/login/',
            MenuImage          = @IconUrl,
            ParentMenu         = 0,
            OrderNo            = ISNULL(OrderNo, @RootOrderNo),
            TargetPage         = N'_blank',
            IsActive           = 1,
            last_modified_date = GETDATE(),
            last_modified_by   = SUSER_SNAME()
        WHERE menuId = @RootMenuId;
    END;

    UPDATE target
    SET
        target.MenuNameThai       = source.ThaiName,
        target.MenuUrl            = @CmsBaseUrl + source.RelativePath,
        target.MenuImage          = @IconUrl,
        target.ParentMenu         = @RootMenuId,
        target.OrderNo            = source.OrderNo,
        target.TargetPage         = N'_self',
        target.IsActive           = 1,
        target.last_modified_date = GETDATE(),
        target.last_modified_by   = SUSER_SNAME()
    FROM dbo.Sysmenu AS target
    INNER JOIN @Menus AS source
        ON source.MenuKey = target.menu_name_eng;

    INSERT INTO dbo.Sysmenu (
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
        source.MenuKey,
        source.ThaiName,
        @CmsBaseUrl + source.RelativePath,
        @IconUrl,
        @RootMenuId,
        source.OrderNo,
        N'_self',
        1,
        GETDATE(),
        SUSER_SNAME()
    FROM @Menus AS source
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.Sysmenu AS existing
        WHERE existing.menu_name_eng = source.MenuKey
    );

    IF (
        SELECT COUNT(*)
        FROM dbo.Sysmenu
        WHERE ParentMenu = @RootMenuId
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
        THROW 50004, N'สร้างหรือย้ายเมนูย่อยไม่ครบ 7 รายการ', 1;

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

