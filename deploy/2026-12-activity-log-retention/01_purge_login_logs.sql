-- ลบ log เข้า/ออกระบบที่เก่ากว่า 1 ปี จาก dbo.Contract_activity_log (ผู้ใช้กำหนด 2026-11-26)
--
-- ลบเฉพาะเหตุการณ์ที่ไม่ใช่งานธุรกิจ -- โตตามจำนวนครั้งที่ล็อกอิน ไม่ใช่ตามงานจริง:
--   login, logout, login_failed      (meters/signals.py)
--   view_as_start, view_as_stop      (ผู้ดูแลระบบดูในมุมมองกลุ่ม)
-- log งานธุรกิจ (ยกเลิกสัญญา มิเตอร์ นำเข้า/ดาวน์โหลด Excel ใบแจ้งหนี้ ฯลฯ) เก็บไว้ตลอด ไม่แตะ
--
-- ค่าเริ่มต้น @DryRun = 1 = นับอย่างเดียว ไม่ลบ -- เปลี่ยนเป็น 0 เมื่อจะลบจริง
-- ลบทีละ @BatchSize แถว แต่ละชุดเป็น Transaction ของตัวเอง ไม่ล็อกตารางนาน รันซ้ำได้
-- ใช้เป็น Step ของ SQL Agent Job (ดู README.md) ไม่สร้าง Stored Procedure ไม่แก้ Schema
USE [SWU_contract];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @DryRun bit = 1;
DECLARE @KeepMonths int = 12;
DECLARE @BatchSize int = 5000;

-- ตัดที่เที่ยงคืนของวัน (ไม่ใช่เวลาที่รัน) ให้ผลเหมือนกันทั้งวันไม่ว่ารันกี่โมง
DECLARE @Cutoff datetime = DATEADD(month, -@KeepMonths, CONVERT(date, GETDATE()));

DECLARE @Actions table (Action_type varchar(40) NOT NULL PRIMARY KEY);
INSERT INTO @Actions (Action_type) VALUES
    ('login'), ('logout'), ('login_failed'), ('view_as_start'), ('view_as_stop');

IF @KeepMonths < 12
    THROW 50010, N'@KeepMonths ต้องไม่น้อยกว่า 12 (ผู้ใช้กำหนดเก็บอย่างน้อย 1 ปี)', 1;

-- นับก่อนลบ (ใช้ index IX_Contract_activity_log_Action = Action_type, DateEntry)
SELECT g.Action_type, COUNT(*) AS RowsOlderThanCutoff, MIN(g.DateEntry) AS Oldest, @Cutoff AS Cutoff
FROM dbo.Contract_activity_log g
INNER JOIN @Actions a ON a.Action_type = g.Action_type
WHERE g.DateEntry < @Cutoff
GROUP BY g.Action_type
ORDER BY g.Action_type;

IF @DryRun = 1
BEGIN
    PRINT N'DryRun: ยังไม่ได้ลบ -- ตั้ง @DryRun = 0 เพื่อลบจริง';
    RETURN;
END;

DECLARE @Deleted int = 1;
DECLARE @Total int = 0;

WHILE @Deleted > 0
BEGIN
    BEGIN TRANSACTION;

    DELETE TOP (@BatchSize) g
    FROM dbo.Contract_activity_log g
    WHERE g.DateEntry < @Cutoff
      AND g.Action_type IN (SELECT Action_type FROM @Actions);

    SET @Deleted = @@ROWCOUNT;
    SET @Total += @Deleted;

    COMMIT TRANSACTION;

    -- เว้นจังหวะให้งานอื่นที่เขียน log อยู่ได้ทำต่อ
    IF @Deleted > 0 WAITFOR DELAY '00:00:01';
END;

SELECT @Total AS DeletedRows, @Cutoff AS Cutoff, GETDATE() AS FinishedAt;
