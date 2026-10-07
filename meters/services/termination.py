# meters/services/termination.py
from .db import get_db_connection
from .meters import _to_sql_like_pattern

# สถานะสัญญาที่ยกเลิกซ้ำไม่ได้ (อ้างจาก dbo.Contract_status_ms)
#   '4' ไม่ต่อสัญญา / '5' ยกเลิกสัญญา -> เป็นผลลัพธ์ของการยกเลิกอยู่แล้ว
#   '9' ปิดสัญญา                       -> ปิดจบแล้ว
# ค่าชุดเดียวกันนี้ถูกบังคับใน sp_Contract_Termination_Save ด้วย (เป็นด่านจริง)
# ที่นี่ใช้เพื่อ "ปิดฟอร์มล่วงหน้า" ให้ผู้ใช้รู้ก่อนกรอก ไม่ใช่กรอกเสร็จแล้วเพิ่งโดนปฏิเสธ
BLOCKED_CONTRACT_STATUSES = frozenset({'4', '5', '9'})


def fetch_contracts_for_termination(search='', status='all'):
    """
    รายการสัญญาสำหรับหน้ายกเลิกสัญญา -- คืนทุกแถวที่ตรงเงื่อนไข (ไม่จำกัดจำนวน)

    เดิมเป็น find_contract_for_termination ที่บังคับให้ค้นหาก่อนจึงเห็นอะไร และจำกัด
    50 แถว ตอนนี้หน้ากลายเป็นหน้ารายการ + ตัวกรอง จึงดึงมาทั้งชุดแล้วให้ view
    นับจำนวนต่อแท็บและแบ่งหน้าเอง -- ทั้งระบบมี 224 สัญญา ปริมาณไม่เป็นปัญหา
    และการนับต่อแท็บต้องเห็นข้อมูลทั้งชุดอยู่ดี (ถ้าตัดใน SQL ตัวเลขบนแท็บจะผิด)

    search -- บางส่วนของรหัสสัญญา หรือชื่อบริษัทลูกค้า (ว่าง = ไม่กรอง)
    status -- Status_contract_id ที่ต้องการ หรือ 'all'

    คืนคอลัมน์ที่หน้ารายการต้องใช้:
      Has_termination    -- มีรายการยกเลิกในระบบนี้แล้วหรือยัง (ใช้แยกแท็บ)
      End_contract       -- ใช้คำนวณว่าหมดอายุหรือยัง และใช้เรียงลำดับ
      Status_workflow__id + Status_workflow_Desc -- ใช้แยกสัญญาจริงกับฉบับร่าง
      Has_installment    -- มีงวดตั้งหนี้แล้วหรือยัง (ใช้คู่กับ workflow)

    เรียงตาม End_contract เก่าสุดก่อน = ค้างนานสุด = ควรจัดการก่อน
    สัญญาที่ไม่มี End_contract ไปอยู่ท้ายสุด (ไม่รู้ลำดับความสำคัญ ไม่ควรอยู่หัวแถว)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT c.Contract_id, c.Contract_code, c.Contract_year,
                   c.Status_contract_id, s.Status_contract_Desc,
                   cu.CompanyName,
                   CAST(CASE WHEN t.Contract_id IS NULL THEN 0 ELSE 1 END AS int) AS Has_termination,
                   ct.Start_contract, ct.End_contract,
                   -- สถานะ workflow ของสัญญา -- ใช้แยกว่าเป็นสัญญาจริงหรือยังเป็นร่าง
                   -- (ชื่อคอลัมน์ใน Contract_hrd_tr มี underscore สองตัว แต่ใน master มีตัวเดียว)
                   c.Status_workflow__id, w.Status_workflow_Desc,
                   -- มีงวดตั้งหนี้แล้วหรือยัง -- ข้อมูลจริงมี 24 สัญญาที่ workflow ยังค้างเป็นร่าง
                   -- แต่ตั้งหนี้ไปแล้ว (บางฉบับ 53 งวด) จึงใช้ workflow ตัวเดียวตัดสินไม่ได้
                   CAST(CASE WHEN EXISTS (
                       SELECT 1 FROM dbo.Contract_Installment_tr i WHERE i.Contract_id = c.Contract_id
                   ) THEN 1 ELSE 0 END AS int) AS Has_installment
            FROM dbo.Contract_hrd_tr c
            LEFT JOIN dbo.Contract_status_ms s ON s.Status_contract_id = c.Status_contract_id
            LEFT JOIN dbo.Contract_workflow_status_ms w ON w.Status_workflow_id = c.Status_workflow__id
            LEFT JOIN dbo.Contract_termination_tr t ON t.Contract_id = c.Contract_id
            LEFT JOIN dbo.Contract_tr ct ON ct.Contract_id = c.Contract_id
            -- Contract_customer_tr.Contract_id เป็น nvarchar(50) ส่วน Contract_hrd_tr.Contract_id
            -- เป็น int -- join ตรงๆ จะเป็น implicit convert ที่พังทั้ง query ถ้ามีแถวไหน
            -- เก็บข้อความที่ไม่ใช่ตัวเลข จึงใช้ TRY_CONVERT + OUTER APPLY TOP 1
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = c.Contract_id
            ) cu
            WHERE 1 = 1
        """
        params = []

        search = (search or '').strip()
        if search:
            # escape wildcard ที่ผู้ใช้พิมพ์มาจริง (% _ [) ไม่ให้ถูกตีความเป็น wildcard ของ SQL
            # ไม่งั้นค้นหา '%' จะคืนสัญญาทั้งหมดในระบบ
            like = _to_sql_like_pattern(search)
            sql += ' AND (LTRIM(RTRIM(c.Contract_code)) LIKE ? OR cu.CompanyName LIKE ?)'
            params += [like, like]

        if status and status != 'all':
            sql += ' AND c.Status_contract_id = ?'
            params.append(status)

        # CASE WHEN ... IS NULL THEN 1 ELSE 0 -> ดันแถวที่ไม่มีวันสิ้นสุดไปท้ายสุด
        sql += """
            ORDER BY CASE WHEN ct.End_contract IS NULL THEN 1 ELSE 0 END,
                     ct.End_contract,
                     c.Contract_code, c.Contract_id
        """

        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_contract_statuses():
    """
    รายการสถานะสัญญาจาก Contract_status_ms สำหรับ dropdown ตัวกรอง
    ดึงเฉพาะสถานะที่มีสัญญาใช้อยู่จริง -- ไม่เอาตัวเลือกที่กดแล้วได้ 0 แถวมารกหน้าจอ
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.Status_contract_id, s.Status_contract_Desc, COUNT(c.Contract_id) AS Contract_count
            FROM dbo.Contract_status_ms s
            INNER JOIN dbo.Contract_hrd_tr c ON c.Status_contract_id = s.Status_contract_id
            GROUP BY s.Status_contract_id, s.Status_contract_Desc
            ORDER BY s.Status_contract_id
            """
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_contract_summary(contract_id):
    """
    ข้อมูลระบุตัวสัญญาสำหรับหัวหน้า termination_detail -- รหัสสัญญา ชื่อลูกค้า สถานะปัจจุบัน
    และช่วงอายุสัญญา (Start_contract / End_contract จาก Contract_tr)

    จำเป็นเพราะหน้านี้บันทึกได้ครั้งเดียวและแก้ไม่ได้ แต่เดิมหัวหน้าขึ้นแค่
    "Contract_id #1" ผู้ใช้ไม่มีทางรู้ว่าเข้าสัญญาถูกตัวหรือเปล่าก่อนกดบันทึก

    End_contract ใช้เติมค่า "วันที่สิ้นสุดสัญญา" ในฟอร์มให้อัตโนมัติ -- เดิมผู้ใช้ต้อง
    พิมพ์เอง ซึ่งเสี่ยงมากเพราะวันนี้เป็นตัวคำนวณจำนวนงวดและงวดสุดท้ายทั้งหมด

    คืน None ถ้าไม่พบสัญญา -> view จะตอบ 404 แทนการโชว์ฟอร์มเปล่าที่กดบันทึกแล้วพัง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.Contract_id, c.Contract_code, c.Contract_year,
                   c.Status_contract_id, s.Status_contract_Desc,
                   c.Contract_signer_date_swu, c.Contract_target_desc,
                   cu.CompanyName, cu.Vendor_tel, cu.Customer_id, cu.TaxNumber,
                   cu.SAPVendor_Id,
                   ct.Start_contract, ct.End_contract, ct.Contract_Installment_age,
                   -- สถานะ workflow -- ถ้าสัญญาที่กำลังจะยกเลิกยังเป็นฉบับร่าง ควรเห็นก่อนบันทึก
                   c.Status_workflow__id, w.Status_workflow_Desc,
                   -- ชื่อ/เลขภาษีจาก master ฝั่ง SAP (Contract_Customer_SAP_ms)
                   -- ไม่เอามาแทนค่าใน Contract_customer_tr เพราะข้อมูลจริงมี 3 สัญญาที่ชื่อ
                   -- สองฝั่งเป็นคนละคนกัน (เช่น Contract_id 9, 19, 189) -- เอามาแสดงคู่กัน
                   -- แล้วให้ view เตือนเมื่อไม่ตรง ดีกว่าเปลี่ยนว่าสัญญาเป็นของใครแบบเงียบๆ
                   sap.CompanyName AS SAP_CompanyName,
                   sap.TaxNumber   AS SAP_TaxNumber
            FROM dbo.Contract_hrd_tr c
            LEFT JOIN dbo.Contract_status_ms s ON s.Status_contract_id = c.Status_contract_id
            LEFT JOIN dbo.Contract_workflow_status_ms w ON w.Status_workflow_id = c.Status_workflow__id
            -- Contract_tr เก็บช่วงอายุสัญญา (Start_contract / End_contract)
            -- PK เป็น Contract_id ตรง 1:1 กับ Contract_hrd_tr (224 แถวเท่ากัน) แต่ใช้ LEFT JOIN
            -- ไว้กันกรณีสัญญาที่ยังไม่มีแถวใน Contract_tr -- จะได้ไม่ทำให้หน้าหายทั้งหน้า
            -- ความหมายคอลัมน์ยืนยันจากคอมเมนต์ใน dbo.DueDateForContract:
            --   "@End_contract วันที่ สิ้นสุดสัญญา"
            LEFT JOIN dbo.Contract_tr ct ON ct.Contract_id = c.Contract_id
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName, x.Vendor_tel, x.Customer_id, x.TaxNumber, x.SAPVendor_Id
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = c.Contract_id
            ) cu
            -- ต้องล้าง CR/LF ด้วย ไม่ใช่แค่ LTRIM/RTRIM:
            -- LTRIM/RTRIM ของ SQL Server ตัดเฉพาะ "ช่องว่าง" ไม่ตัด CHAR(13)/CHAR(10)
            -- ข้อมูลจริงมี SAPVendor_Id ที่มี CR/LF ต่อท้ายอยู่ 21 แถวใน Contract_customer_tr
            -- และ 15 แถวใน Contract_Customer_SAP_ms -- ถ้า TRIM เฉยๆ จะจับคู่พลาด 30 แถว
            -- (169 -> 199 จาก 215 แถว หลังล้าง CR/LF)
            --
            -- join ด้วย SAPVendor_Id ไม่ใช่ Customer_id เพราะเป็นคีย์จริงของ master
            -- และให้ผลดีกว่า: จับคู่ได้มากกว่า และชื่อไม่ตรงกันน้อยกว่า (3 แถว เทียบกับ 5 แถว)
            LEFT JOIN dbo.Contract_Customer_SAP_ms sap
                ON LTRIM(RTRIM(REPLACE(REPLACE(sap.SAPVendor_Id, CHAR(13), ''), CHAR(10), '')))
                 = LTRIM(RTRIM(REPLACE(REPLACE(cu.SAPVendor_Id,  CHAR(13), ''), CHAR(10), '')))
            WHERE c.Contract_id = ?
            """,
            contract_id,
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [c[0] for c in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def save_termination(contract_id, contract_code, termination_case, contract_end_date,
                      notify_date, remark, user_id):
    """
    เรียก sp_Contract_Termination_Save -- ยืนยัน parameter ครบ 7 ตัวจาก schema จริงแล้ว:
    @Contract_id, @Contract_code, @Termination_case, @Contract_end_date,
    @Notify_date, @Remark, @UserId (เดิมลืมใส่ @Contract_code ไปตัวหนึ่ง)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_Contract_Termination_Save
                @Contract_id       = ?,
                @Contract_code     = ?,
                @Termination_case  = ?,
                @Contract_end_date = ?,
                @Notify_date       = ?,
                @Remark            = ?,
                @UserId            = ?
            """,
            contract_id, contract_code, termination_case, contract_end_date, notify_date, remark, user_id,
        )
        row = cursor.fetchone()
        columns = [c[0] for c in cursor.description] if cursor.description else []
        result = dict(zip(columns, row)) if row else None
        conn.commit()
        return result
    finally:
        conn.close()


def delete_termination(contract_id, user_id):
    """
    ลบรายการยกเลิกสัญญา (สำหรับกรณีบันทึกผิด) -- เรียก sp_Contract_Termination_Delete

    SP จัดการให้ครบในทรานแซกชันเดียว: ล็อกแถวเดิมลง Contract_termination_tr_log,
    ลบรายการงวด, ลบหัวข้อมูล, แล้วคืน Contract_hrd_tr.Status_contract_id กลับเป็น
    Prev_status_contract_id ที่บันทึกไว้ตอน save

    คืน dict: Termination_id, Restored_status_contract_id, Status_restored
    Status_restored = 0 หมายถึงลบสำเร็จแต่ไม่ได้คืนสถานะสัญญา (แถวเก่าที่ไม่มี
    Prev_status_contract_id) -- view ต้องเอาไปเตือนผู้ใช้ให้ไปตรวจสถานะเอง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_Contract_Termination_Delete
                @Contract_id   = ?,
                @Contract_code = ?,
                @UserId        = ?
            """,
            contract_id, None, user_id,
        )
        row = cursor.fetchone()
        columns = [c[0] for c in cursor.description] if cursor.description else []
        result = dict(zip(columns, row)) if row else None
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def close_meter_billing(contract_id, user_id):
    """
    ปิดการตั้งหนี้มิเตอร์ของสัญญาที่ยกเลิกแล้ว -- เรียก sp_Contract_Termination_CloseMeterBilling

    ตั้ง Contract_meter_tr.UseOrNot = 0 (ตัว transaction ที่ผูกมิเตอร์เข้ากับสัญญา)
    ไม่แตะ Contract_meter_ms -- มิเตอร์เป็นของกายภาพติดอยู่กับพื้นที่ ผู้เช่ารายใหม่
    ยังต้องใช้ตัวเดิม จึงปิดแค่การผูกกับสัญญา ไม่ปิดทะเบียน
    (ด้วยเหตุนี้จึงไม่ใช้ sp_Contract_Meter_Deactivate ที่มีอยู่ -- ตัวนั้นปิดทะเบียน)

    คืนจำนวนแถวที่ปิด
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "EXEC dbo.sp_Contract_Termination_CloseMeterBilling @Contract_id = ?, @UserId = ?",
            contract_id, user_id,
        )
        row = cursor.fetchone()
        closed = int(row[0]) if row else 0
        conn.commit()
        return closed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_meter_bindings(contract_id):
    """
    นับการผูกมิเตอร์ของสัญญา แยกที่ยังตั้งหนี้อยู่กับที่ปิดแล้ว
    ใช้บอกสถานะบนหน้ายกเลิกสัญญาว่าปิดการตั้งหนี้มิเตอร์ไปแล้วหรือยัง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT CAST(SUM(CASE WHEN UseOrNot = 1 THEN 1 ELSE 0 END) AS int) AS active,
                   CAST(SUM(CASE WHEN UseOrNot = 0 THEN 1 ELSE 0 END) AS int) AS closed
            FROM dbo.Contract_meter_tr
            WHERE Contract_id = ?
            """,
            contract_id,
        )
        row = cursor.fetchone()
        return {'active': (row[0] or 0) if row else 0,
                'closed': (row[1] or 0) if row else 0}
    finally:
        conn.close()


def fetch_termination_history(contract_id):
    """
    ประวัติรายการยกเลิกที่ถูกลบของสัญญาหนึ่ง (จาก Contract_termination_tr_log)

    ข้อมูลถูกเก็บไว้แล้วตอนลบ แต่เดิมไม่มีที่ไหนเอามาแสดง -- ถ้ามีคนลบรายการ
    แล้วบันทึกใหม่ จะไม่มีใครเห็นบนหน้าเว็บว่ารายการก่อนหน้าเป็นอะไร
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT g.id, g.Termination_id, g.Termination_case,
                   CASE g.Termination_case
                        WHEN 1 THEN N'ยกเลิกสัญญาก่อนครบอายุ'
                        ELSE N'สิ้นสุดตามอายุสัญญา (ไม่ต่อสัญญา)'
                   END AS Termination_case_name,
                   g.Status_contract_id, s.Status_contract_Desc,
                   g.Prev_status_contract_id, ps.Status_contract_Desc AS Prev_status_contract_Desc,
                   g.Contract_end_date, g.Notify_date, g.Buffer_month_count,
                   g.Last_installment_period, g.Remark,
                   g.UserEntry, g.DateEntry, g.UserDelete, g.DateDelete
            FROM dbo.Contract_termination_tr_log g
            LEFT JOIN dbo.Contract_status_ms s  ON s.Status_contract_id = g.Status_contract_id
            LEFT JOIN dbo.Contract_status_ms ps ON ps.Status_contract_id = g.Prev_status_contract_id
            WHERE g.Contract_id = ?
            ORDER BY g.DateDelete DESC, g.id DESC
            """,
            contract_id,
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


# ประเภทเหตุการณ์ในหน้าประวัติ (?event=)
LOG_EVENT_SAVED = 'saved'
LOG_EVENT_DELETED = 'deleted'
LOG_EVENT_ALL = 'all'

TERMINATION_LOG_EVENTS = [
    (LOG_EVENT_ALL, 'ทุกเหตุการณ์'),
    (LOG_EVENT_SAVED, 'บันทึกยกเลิก'),
    (LOG_EVENT_DELETED, 'ลบรายการยกเลิก'),
]


def fetch_termination_log(search=''):
    """
    ประวัติการยกเลิกสัญญาทั้งระบบ เรียงตามเวลาล่าสุดก่อน

    รวมเหตุการณ์จาก 2 ตารางด้วย UNION ALL:
      1) Contract_termination_tr      -> 'saved'   (รายการที่ยังอยู่)
      2) Contract_termination_tr_log  -> 'saved'   (รายการที่ถูกลบ -- ตอนที่เคยถูกบันทึก)
      3) Contract_termination_tr_log  -> 'deleted' (ตอนที่ถูกลบ)

    รายการที่ถูกลบจึงปรากฏ 2 เหตุการณ์ (บันทึก แล้วลบ) ทำให้เห็นลำดับเวลาครบ

    ไม่รวมเหตุการณ์ "ปิดการตั้งหนี้มิเตอร์" เพราะ Contract_meter_tr เก็บแค่
    DateUpdate ล่าสุดของแต่ละแถว ซึ่งถูกเขียนทับเมื่อคืนค่า -- เอามาทำ timeline
    แล้วจะให้ข้อมูลที่เข้าใจผิดได้ (ดูสถานะปัจจุบันที่หน้ารายละเอียดสัญญาแทน)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            WITH events AS (
                SELECT t.Contract_id, t.Termination_id, t.Termination_case,
                       t.Last_installment_period, t.Remark,
                       'saved' AS Event_type, t.UserEntry AS Event_user, t.DateEntry AS Event_at,
                       CAST(1 AS int) AS Is_current
                FROM dbo.Contract_termination_tr t
                UNION ALL
                SELECT g.Contract_id, g.Termination_id, g.Termination_case,
                       g.Last_installment_period, g.Remark,
                       'saved', g.UserEntry, g.DateEntry, CAST(0 AS int)
                FROM dbo.Contract_termination_tr_log g
                UNION ALL
                SELECT g.Contract_id, g.Termination_id, g.Termination_case,
                       g.Last_installment_period, g.Remark,
                       'deleted', g.UserDelete, g.DateDelete, CAST(0 AS int)
                FROM dbo.Contract_termination_tr_log g
            )
            SELECT e.Contract_id, c.Contract_code, cu.CompanyName,
                   e.Termination_id, e.Termination_case,
                   CASE e.Termination_case
                        WHEN 1 THEN N'ยกเลิกสัญญาก่อนครบอายุ'
                        ELSE N'สิ้นสุดตามอายุสัญญา (ไม่ต่อสัญญา)'
                   END AS Termination_case_name,
                   e.Last_installment_period, e.Remark,
                   e.Event_type, e.Event_user, e.Event_at, e.Is_current
            FROM events e
            LEFT JOIN dbo.Contract_hrd_tr c ON c.Contract_id = e.Contract_id
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = e.Contract_id
            ) cu
            WHERE 1 = 1
        """
        params = []
        search = (search or '').strip()
        if search:
            like = _to_sql_like_pattern(search)
            sql += """ AND (LTRIM(RTRIM(c.Contract_code)) LIKE ?
                            OR cu.CompanyName LIKE ?
                            OR e.Event_user LIKE ?)"""
            params += [like, like, like]

        sql += ' ORDER BY e.Event_at DESC, e.Termination_id DESC'

        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_termination_detail(contract_id=None, contract_code=None):
    """
    เรียก sp_Contract_Termination_SelectByContract -- SP นี้คืน 2 result set
    (หัวข้อมูลยกเลิก + รายการงวด) ต้องใช้ cursor.nextset() ไล่อ่านทีละชุด
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "EXEC dbo.sp_Contract_Termination_SelectByContract @Contract_id = ?, @Contract_code = ?",
            contract_id, contract_code,
        )
        header = None
        if cursor.description:
            columns = [c[0] for c in cursor.description]
            row = cursor.fetchone()
            header = dict(zip(columns, row)) if row else None

        periods = []
        if cursor.nextset() and cursor.description:
            columns2 = [c[0] for c in cursor.description]
            periods = [dict(zip(columns2, r)) for r in cursor.fetchall()]

        return header, periods
    finally:
        conn.close()


_SP_SET_SELECTION = """
    EXEC dbo.sp_Contract_Termination_SetInstallmentSelection
        @Termination_id     = ?,
        @Installment_period = ?,
        @Is_selected        = ?,
        @UserId             = ?
"""


def set_installment_selection(termination_id, installment_period, is_selected, user_id):
    """เรียก sp_Contract_Termination_SetInstallmentSelection -- ติ๊กเลือก/ยกเลิกงวดเดียว"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            _SP_SET_SELECTION,
            termination_id, installment_period, 1 if is_selected else 0, user_id,
        )
        conn.commit()
    finally:
        conn.close()


def set_all_installment_selections(termination_id, is_selected, user_id):
    """
    ติ๊ก/ยกเลิกงวดทั้งหมดของการยกเลิกสัญญานี้ในคราวเดียว

    เดิมผู้ใช้ต้องกดทีละงวด ซึ่งแต่ละครั้งคือ 1 request + reload หน้าใหม่
    กรณีผ่อนผัน 2 เดือนอาจมีงวดถึง 25 งวด (ขอบเขตที่ SP จำกัดไว้)

    ยังเรียกผ่าน SP เดิมทีละงวด (ไม่เขียน UPDATE ตรงเข้าตาราง เพื่อคงสถาปัตยกรรมที่
    การเขียนข้อมูลผ่าน stored procedure เท่านั้น) แต่ใช้ connection เดียวและ commit
    ครั้งเดียวตอนท้าย -- ถ้างวดใดพลาด จะ rollback ทั้งชุด ไม่เหลือสถานะครึ่งๆ กลางๆ

    คืนจำนวนงวดที่อัปเดต
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT Installment_period
            FROM dbo.Contract_termination_installment_dt
            WHERE Termination_id = ?
            ORDER BY Installment_period
            """,
            termination_id,
        )
        periods = [row[0] for row in cursor.fetchall()]

        flag = 1 if is_selected else 0
        for period in periods:
            cursor.execute(_SP_SET_SELECTION, termination_id, period, flag, user_id)

        conn.commit()
        return len(periods)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()