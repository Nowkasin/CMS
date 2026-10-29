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
  - เหตุการณ์อื่นทั้งหมด เขียนจากฝั่ง Python (view) หลังงานหลัก commit สำเร็จแล้ว
    ผ่าน log_activity_safe() -- ถ้าเขียน log พลาดจะไม่ทำให้งานหลักที่สำเร็จไปแล้วดูเหมือนล้ม

ไม่บันทึก (ตั้งใจ):
  - การติ๊กงวดทีละงวดในหน้ายกเลิกสัญญา -- เกิดบ่อย เป็นแค่ข้อมูลอ้างอิง
    ถ้าลงทุกครั้ง หน้า log จะถูกกลบด้วยรายการเล็กๆ จนหาเหตุการณ์สำคัญไม่เจอ
  - การเปิดดูหน้าต่างๆ (GET) -- log นี้เก็บเฉพาะการเปลี่ยนแปลงข้อมูลและการนำข้อมูลออก
"""
import logging

from django.urls import NoReverseMatch, reverse

from .db import get_db_connection
from .meters import _to_sql_like_pattern

logger = logging.getLogger(__name__)

# ประเภทเหตุการณ์ -- key คือค่าที่เก็บใน Contract_activity_log.Action_type
# (ยาวสุดที่ใช้อยู่คือ termination_close_meters 24 ตัวอักษร -- ชื่อใหม่ให้ไม่ยาวกว่านี้
#  เพราะยังไม่ได้เช็คขนาดคอลัมน์ Action_type จริง)

# --- เดิม ---
ACTION_UPLOAD_COMMIT = 'upload_commit'
ACTION_TERMINATION_SAVE = 'termination_save'
ACTION_TERMINATION_DELETE = 'termination_delete'
ACTION_TERMINATION_CLOSE_METERS = 'termination_close_meters'

# --- ใหม่: ทะเบียนมิเตอร์ ---
ACTION_METER_CREATE = 'meter_create'          # เพิ่มมิเตอร์ใหม่ (หน้าจัดการมิเตอร์)
ACTION_METER_UPDATE = 'meter_update'          # แก้ไขมิเตอร์ (หน้าจัดการมิเตอร์)
ACTION_METER_TOGGLE = 'meter_toggle'          # เปิด/ปิดใช้งานมิเตอร์
ACTION_READING_SAVE = 'reading_save'          # แก้เลขมิเตอร์/เลขอ่านรายรอบ (หน้าแดชบอร์ด > แก้ไข)

# --- ใหม่: Master ระบบไฟฟ้า ---
ACTION_PHASE_CREATE = 'phase_create'
ACTION_PHASE_UPDATE = 'phase_update'
ACTION_PHASE_TOGGLE = 'phase_toggle'          # เปิด/ปิดใช้งานอย่างเดียว ไม่ได้แก้ชื่อ

# --- ใหม่: นำข้อมูลออก ---
ACTION_DOWNLOAD_EXCEL = 'download_excel'      # ดาวน์โหลด Excel (เดือน-ปี + จำนวนรายการ)
ACTION_EXPORT_METERS = 'export_meters'        # ส่งออก Excel จากแดชบอร์ด

# --- ใหม่: POST ที่ยังไม่ได้ลงทะเบียนใน middleware ---
ACTION_OTHER = 'other_action'

# ลำดับในนี้คือลำดับแท็บบนหน้า log
ACTIVITY_ACTIONS = [
    (ACTION_UPLOAD_COMMIT, 'นำเข้าไฟล์ Excel'),
    (ACTION_DOWNLOAD_EXCEL, 'ดาวน์โหลด Excel'),
    (ACTION_EXPORT_METERS, 'ส่งออกมิเตอร์'),
    (ACTION_METER_CREATE, 'เพิ่มมิเตอร์'),
    (ACTION_METER_UPDATE, 'แก้ไขมิเตอร์'),
    (ACTION_METER_TOGGLE, 'เปิด/ปิดมิเตอร์'),
    (ACTION_READING_SAVE, 'แก้เลขมิเตอร์/เลขอ่าน'),
    (ACTION_PHASE_CREATE, 'เพิ่มระบบไฟฟ้า'),
    (ACTION_PHASE_UPDATE, 'แก้ไขระบบไฟฟ้า'),
    (ACTION_PHASE_TOGGLE, 'เปิด/ปิดระบบไฟฟ้า'),
    (ACTION_TERMINATION_SAVE, 'บันทึกยกเลิกสัญญา'),
    (ACTION_TERMINATION_DELETE, 'ลบรายการยกเลิก'),
    (ACTION_TERMINATION_CLOSE_METERS, 'ปิดการตั้งหนี้มิเตอร์'),
    (ACTION_OTHER, 'การดำเนินการอื่น'),
]

# ชื่อเหตุการณ์ที่ไม่รู้จัก (เผื่อมี Action_type ในฐานข้อมูลที่ยังไม่ได้ลงทะเบียนที่นี่
# เช่นถูกเขียนจาก SP ที่เพิ่มภายหลัง) -- แสดงค่าดิบดีกว่าซ่อนแถวนั้นไป
ACTION_LABELS = dict(ACTIVITY_ACTIONS)

# ตัดข้อความก่อนส่งเข้า SP กันล้นคอลัมน์ -- ยังไม่ได้เช็คขนาด Ref_text/Detail จริง
# ถ้าคอลัมน์จริงสั้นกว่านี้ให้ลดค่าลงให้ตรง
MAX_REF_TEXT_LEN = 200
MAX_DETAIL_LEN = 500


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


def log_activity_safe(action_type, user_id, **kwargs):
    """
    เขียน log แบบ "พลาดได้โดยไม่กระทบงานหลัก" -- ใช้จาก view หลังงานหลัก commit แล้ว

    ทำไมต้องมี: view ส่วนใหญ่ครอบงานหลักด้วย try/except Exception แล้วแสดง
    "บันทึกไม่สำเร็จ" ถ้าเรียก add_activity_log ตรงๆ ในบล็อกเดียวกัน แล้ว log พลาด
    ผู้ใช้จะเห็นว่าบันทึกไม่สำเร็จทั้งที่ข้อมูลหลักถูกบันทึกไปแล้ว และกดซ้ำจนซ้ำซ้อน

    ฟังก์ชันนี้เปิด connection ของตัวเอง (ไม่รับ cursor) และกลืน error ลง logger
    -- ผลเสียคือ log อาจหายเงียบๆ ได้ ให้ดู error ในล็อกของเซิร์ฟเวอร์ (logger 'meters.services.activity_log')

    ห้ามใช้ในโค้ดที่อยู่ในทรานแซกชันเดียวกับงานหลัก (ที่ส่ง cursor เข้า add_activity_log)
    เพราะต้องการให้ล้มพร้อมกัน

    คืน True ถ้าเขียนสำเร็จ
    """
    for key, limit in (('ref_text', MAX_REF_TEXT_LEN), ('detail', MAX_DETAIL_LEN)):
        value = kwargs.get(key)
        if value is not None:
            value = str(value)
            kwargs[key] = value if len(value) <= limit else value[:limit - 1] + '…'
    try:
        add_activity_log(action_type, user_id, **kwargs)
        return True
    except Exception:
        logger.exception('เขียน activity log ไม่สำเร็จ (action=%s, user=%s)', action_type, user_id)
        return False


def _row_link(row):
    """
    ปุ่มลัดของคอลัมน์ "ดำเนินการ" -- คืน (url, ข้อความปุ่ม) หรือ (None, None) ถ้าไม่มีหน้าที่เกี่ยวข้อง

    เลือกตามประเภทเหตุการณ์ ไม่ใช่ดูว่ามี id อะไรบ้าง เพราะเหตุการณ์ต่างชนิดเก็บ id ปนกันได้
    (เช่นเลขอ่านเก็บทั้ง Contract_id และ SubArea_id แต่ปุ่มที่ควรเป็นคือไปหน้าพื้นที่นั้น)
    ระบบไฟฟ้าไม่มีคอลัมน์เก็บ id ของรายการใน log จึงพาไปหน้ารายการ ไม่ใช่หน้าแก้ไขตรงตัว
    """
    action = row.get('Action_type')
    try:
        if action in (ACTION_METER_UPDATE, ACTION_METER_TOGGLE) and row.get('Meter_id'):
            return reverse('meter_edit', args=[row['Meter_id']]), 'ดูมิเตอร์ ›'
        if action == ACTION_READING_SAVE and row.get('SubArea_id'):
            return reverse('edit_meter', args=[row['SubArea_id']]), 'ดูพื้นที่ ›'
        if action in (ACTION_PHASE_CREATE, ACTION_PHASE_UPDATE, ACTION_PHASE_TOGGLE):
            return reverse('phase_list'), 'ดูระบบไฟฟ้า ›'
        if row.get('Contract_id'):
            return reverse('termination_detail', args=[row['Contract_id']]), 'ดูสัญญา ›'
    except NoReverseMatch:
        pass
    return None, None


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
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for r in rows:
            r['action_url'], r['action_text'] = _row_link(r)
        return rows
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