# meters/services/activity_log.py
"""
log เหตุการณ์รวมของระบบ (dbo.Contract_activity_log)

ทำไมต้องมี: ทุกตารางที่ระบบนี้เขียนเก็บแค่สถานะล่าสุด -- UserUpdate/DateUpdate
ถูกเขียนทับทุกครั้งที่แก้ จึงไม่มีประวัติว่าเกิดอะไรขึ้นบ้าง และไม่มีตารางไหน
บันทึกเหตุการณ์การอัปโหลดไฟล์เลย

เจ้าของรายการชื่อ Action_type อยู่ที่ไฟล์นี้ (ฝั่ง DB เก็บเป็น varchar เฉยๆ)

ใครเขียน log ที่ไหน
  - เหตุการณ์ยกเลิกสัญญา 3 อย่าง เขียนใน SP เอง (ทรานแซกชันเดียวกับข้อมูลหลัก)
    ดู sql/Contract_activity_log_Hook_Termination.sql
  - เหตุการณ์นำเข้าไฟล์ Excel เขียนจากฝั่งนี้ เพราะชื่อไฟล์มีอยู่แค่ใน Python
"""
from .db import get_db_connection
from .meters import _to_sql_like_pattern

# ประเภทเหตุการณ์ -- key คือค่าที่เก็บใน Contract_activity_log.Action_type
ACTION_UPLOAD_COMMIT = 'upload_commit'
ACTION_TERMINATION_SAVE = 'termination_save'
ACTION_TERMINATION_DELETE = 'termination_delete'
ACTION_TERMINATION_CLOSE_METERS = 'termination_close_meters'

# ลำดับในนี้คือลำดับแท็บบนหน้า log
ACTIVITY_ACTIONS = [
    (ACTION_UPLOAD_COMMIT, 'นำเข้าไฟล์ Excel'),
    (ACTION_TERMINATION_SAVE, 'บันทึกยกเลิกสัญญา'),
    (ACTION_TERMINATION_DELETE, 'ลบรายการยกเลิก'),
    (ACTION_TERMINATION_CLOSE_METERS, 'ปิดการตั้งหนี้มิเตอร์'),
]

# ชื่อเหตุการณ์ที่ไม่รู้จัก (เผื่อมี Action_type ในฐานข้อมูลที่ยังไม่ได้ลงทะเบียนที่นี่
# เช่นถูกเขียนจาก SP ที่เพิ่มภายหลัง) -- แสดงค่าดิบดีกว่าซ่อนแถวนั้นไป
ACTION_LABELS = dict(ACTIVITY_ACTIONS)


def add_activity_log(action_type, user_id, contract_id=None, meter_id=None,
                     subarea_id=None, ref_text=None, detail=None, cursor=None):
    """
    เขียน log 1 เหตุการณ์ผ่าน sp_Contract_Activity_Log_Add

    cursor -- ถ้าส่ง cursor ที่กำลังทำงานอยู่เข้ามา จะเขียนบน connection เดิม
    (อยู่ในทรานแซกชันเดียวกับงานหลัก ผู้เรียกเป็นคน commit เอง)
    ถ้าไม่ส่ง จะเปิด connection ใหม่และ commit ให้เลย

    การเขียน log ไม่ควรทำให้งานหลักล้ม -- ผู้เรียกที่ส่ง cursor มาเองต้องเป็นคน
    ตัดสินใจเรื่อง error handling เพราะอยู่ในทรานแซกชันเดียวกัน
    """
    sql = """
        EXEC dbo.sp_Contract_Activity_Log_Add
            @Action_type = ?,
            @UserId      = ?,
            @Contract_id = ?,
            @Meter_id    = ?,
            @SubArea_id  = ?,
            @Ref_text    = ?,
            @Detail      = ?
    """
    params = (action_type, user_id, contract_id, meter_id, subarea_id, ref_text, detail)

    if cursor is not None:
        cursor.execute(sql, *params)
        return

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, *params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_activity_log(search='', action='all'):
    """
    ดึง log เหตุการณ์ เรียงเวลาล่าสุดก่อน

    search -- รหัสสัญญา / ชื่อลูกค้า / ชื่อผู้ทำรายการ / ข้อความอ้างอิง
    action -- Action_type ที่ต้องการ หรือ 'all'

    join Contract_hrd_tr เพื่อเอารหัสสัญญามาแสดง (log เก็บแค่ Contract_id)
    และ OUTER APPLY หาชื่อลูกค้า -- Contract_customer_tr.Contract_id เป็น nvarchar
    ส่วน Contract_hrd_tr.Contract_id เป็น int จึงต้องใช้ TRY_CONVERT ไม่ใช่ join ตรงๆ
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT g.Log_id, g.Action_type, g.Contract_id, g.Meter_id, g.SubArea_id,
                   g.Ref_text, g.Detail, g.UserEntry, g.DateEntry,
                   c.Contract_code, cu.CompanyName
            FROM dbo.Contract_activity_log g
            LEFT JOIN dbo.Contract_hrd_tr c ON c.Contract_id = g.Contract_id
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = g.Contract_id
            ) cu
            WHERE 1 = 1
        """
        params = []

        if action and action != 'all':
            sql += ' AND g.Action_type = ?'
            params.append(action)

        search = (search or '').strip()
        if search:
            like = _to_sql_like_pattern(search)
            sql += """ AND (LTRIM(RTRIM(c.Contract_code)) LIKE ?
                            OR cu.CompanyName LIKE ?
                            OR g.UserEntry LIKE ?
                            OR g.Ref_text LIKE ?)"""
            params += [like, like, like, like]

        sql += ' ORDER BY g.DateEntry DESC, g.Log_id DESC'

        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def count_activity_by_action():
    """นับจำนวน log แยกตามประเภทเหตุการณ์ -- ใช้โชว์ตัวเลขบนแท็บ"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT Action_type, COUNT(*) AS n
            FROM dbo.Contract_activity_log
            GROUP BY Action_type
            """
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
    finally:
        conn.close()
