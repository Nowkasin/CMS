# meters/services/phase.py
"""
Master ระบบไฟฟ้า (dbo.Contract_meter_phase_ms) -- ตาราง 1 เฟส / 3 เฟส ที่เอาไปใช้เป็น
ตัวเลือกในช่อง "ระบบไฟฟ้า" ของหน้าจัดการมิเตอร์

ค่าในคอลัมน์ Phase_type คือค่าที่จะถูกเขียนลง Contract_meter_ms.Phase_type จริง
(varchar(10) collation Thai_CI_AS) ส่วน Phase_desc เป็นคำบรรยายสำหรับแสดงบนหน้าจอเท่านั้น

โครงสร้างตารางสร้างโดย sql/Contract_meter_phase_ms_Setup.sql
"""
from .db import get_db_connection

MAX_PHASE_TYPE_LEN = 10   # ตรงกับ varchar(10) ของทั้ง master และ Contract_meter_ms.Phase_type


def fetch_phase_types(status_filter='active'):
    """
    ดึงรายการระบบไฟฟ้าทั้งหมดจาก master พร้อมจำนวนมิเตอร์ที่ใช้อยู่ (meters_using)
    status_filter: 'active' (ค่าเริ่มต้น, UseOrNot=1), 'inactive' (UseOrNot=0), 'all' (ไม่กรอง)

    meters_using ใช้ตอนเตือนก่อนปิดใช้งาน -- ถ้ามีมิเตอร์ผูกอยู่ การปิดจะทำให้ค่าที่บันทึกไว้
    ไม่มีตัวเลือกรองรับในหน้าจอ (ข้อมูลเดิมยังอยู่ ไม่ได้ถูกลบ)
    """
    sql = """
        SELECT p.Phase_id, p.Phase_type, p.Phase_desc, p.UseOrNot,
               p.UserEntry, p.DateEntry, p.UserUpdate, p.DateUpdate,
               (SELECT COUNT(*) FROM dbo.Contract_meter_ms m
                WHERE m.Phase_type = p.Phase_type) AS meters_using
        FROM dbo.Contract_meter_phase_ms p
        WHERE 1=1
    """
    if status_filter == 'active':
        sql += " AND p.UseOrNot = 1"
    elif status_filter == 'inactive':
        sql += " AND p.UseOrNot = 0"
    sql += " ORDER BY p.Phase_id"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_phase_options(current_value=None):
    """
    รายการตัวเลือกสำหรับ dropdown "ระบบไฟฟ้า" ในหน้าจัดการมิเตอร์/แก้ไขมิเตอร์
    คืน list of dict {'Phase_type', 'Phase_desc', 'is_obsolete'}

    ปกติเอาเฉพาะรายการที่เปิดใช้งาน (UseOrNot=1) แต่ถ้ามิเตอร์ตัวที่กำลังแก้บันทึกค่าที่
    ไม่อยู่ในรายการเปิดใช้งาน (เช่นประเภทนั้นถูกปิดใช้งานภายหลัง หรือเป็นข้อมูลเก่าที่ยัง
    ไม่มีใน master) จะเติมค่านั้นเข้าไปเป็นตัวเลือกด้วย พร้อม flag is_obsolete = True
    เพื่อให้เห็นค่าที่บันทึกไว้จริง ไม่ให้หายเงียบๆ กลายเป็น "ไม่ระบุ" ตอนกดบันทึกอีกครั้ง
    """
    options = [
        {
            'Phase_type': p['Phase_type'],
            'Phase_desc': p['Phase_desc'],
            'is_obsolete': False,
        }
        for p in fetch_phase_types('active')
    ]

    current = (current_value or '').strip()
    if current and not any(o['Phase_type'] == current for o in options):
        options.append({'Phase_type': current, 'Phase_desc': None, 'is_obsolete': True})

    return options


def fetch_phase_type_by_id(phase_id):
    """ดึงระบบไฟฟ้า 1 รายการตาม Phase_id -- คืน dict หรือ None ถ้าไม่พบ"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT Phase_id, Phase_type, Phase_desc, UseOrNot,
                   UserEntry, DateEntry, UserUpdate, DateUpdate
            FROM dbo.Contract_meter_phase_ms
            WHERE Phase_id = ?
            """,
            int(phase_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [c[0] for c in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def save_phase_type(phase_type, phase_desc, user_id, phase_id=None, use_or_not=1):
    """
    บันทึกระบบไฟฟ้า -- phase_id=None คือเพิ่มใหม่ (INSERT), มีค่าคือแก้ไข (UPDATE)
    คืนค่า Phase_id ของแถวที่บันทึก

    ตรวจก่อนเขียนทุกครั้ง (raise ValueError ให้ view เอาไปแสดงเป็นข้อความบนฟอร์ม):
      - Phase_type ต้องไม่ว่าง และยาวไม่เกิน 10 อักขระ (ข้อจำกัดของคอลัมน์จริง)
      - Phase_type ต้องไม่ซ้ำกับรายการอื่น (มี UNIQUE constraint คุมอยู่ แต่เช็คก่อน
        เพื่อให้ได้ข้อความไทยที่ผู้ใช้อ่านรู้เรื่อง ไม่ใช่ error ดิบจาก SQL Server)

    ไม่อัปเดต Contract_meter_ms.Phase_type ตามให้อัตโนมัติเมื่อแก้ไขข้อความ -- ถ้าเปลี่ยน
    Phase_type ของรายการที่มีมิเตอร์ผูกอยู่ ข้อมูลเดิมในตารางมิเตอร์จะยังเป็นค่าเก่า
    view จึงต้องเตือนผู้ใช้ก่อน (ดู meters_using จาก fetch_phase_types)
    """
    phase_type = (phase_type or '').strip()
    phase_desc = (phase_desc or '').strip() or None

    if not phase_type:
        raise ValueError('กรุณากรอกชื่อระบบไฟฟ้า')
    if len(phase_type) > MAX_PHASE_TYPE_LEN:
        raise ValueError(
            f'ชื่อระบบไฟฟ้ายาวเกินกำหนด -- ใส่ได้ไม่เกิน {MAX_PHASE_TYPE_LEN} อักขระ '
            f'(ที่กรอกมา {len(phase_type)} อักขระ)'
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # เช็คชื่อซ้ำ (ยกเว้นแถวตัวเอง ตอนแก้ไข)
        if phase_id:
            cursor.execute(
                "SELECT Phase_id FROM dbo.Contract_meter_phase_ms "
                "WHERE LTRIM(RTRIM(Phase_type)) = LTRIM(RTRIM(?)) AND Phase_id <> ?",
                phase_type, int(phase_id),
            )
        else:
            cursor.execute(
                "SELECT Phase_id FROM dbo.Contract_meter_phase_ms "
                "WHERE LTRIM(RTRIM(Phase_type)) = LTRIM(RTRIM(?))",
                phase_type,
            )
        if cursor.fetchone():
            raise ValueError(f"มีระบบไฟฟ้าชื่อ '{phase_type}' อยู่ในระบบแล้ว")

        if phase_id:
            cursor.execute(
                "SELECT 1 FROM dbo.Contract_meter_phase_ms WHERE Phase_id = ?", int(phase_id)
            )
            if not cursor.fetchone():
                raise ValueError('ไม่พบรายการระบบไฟฟ้าที่ต้องการแก้ไข')

            cursor.execute(
                """
                UPDATE dbo.Contract_meter_phase_ms
                SET Phase_type = ?,
                    Phase_desc = ?,
                    UseOrNot   = ?,
                    UserUpdate = ?,
                    DateUpdate = GETDATE()
                WHERE Phase_id = ?
                """,
                phase_type, phase_desc, 1 if use_or_not else 0, user_id, int(phase_id),
            )
            result_id = int(phase_id)
        else:
            # ใช้ OUTPUT INSERTED.Phase_id ให้ INSERT คืน id มาในคำสั่งเดียว
            # (เรียก SELECT SCOPE_IDENTITY() แยก execute ไม่ได้ เพราะ SCOPE_IDENTITY
            #  มีขอบเขตแค่ batch เดียว พอขึ้น batch ใหม่จะได้ NULL)
            cursor.execute(
                """
                INSERT INTO dbo.Contract_meter_phase_ms
                    (Phase_type, Phase_desc, UseOrNot, UserEntry, DateEntry)
                OUTPUT INSERTED.Phase_id
                VALUES (?, ?, ?, ?, GETDATE())
                """,
                phase_type, phase_desc, 1 if use_or_not else 0, user_id,
            )
            result_id = int(cursor.fetchone()[0])

        conn.commit()
        return result_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
