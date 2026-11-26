import calendar
from datetime import date
from django.conf import settings

from .db import get_db_connection


DETAIL_FIELDS = ('Floor_BI', 'Shop_Sell_BI', 'Business_Types_BI', 'Shop_name_BI', 'Objective_Desc_BI')
SNAPSHOT_FIELDS = (
    'SubArea_id', 'Location_id', 'Area_id', 'SubArea_name', 'SubArea_size_meters',
    'Status_Area', 'Contract_id', 'Contract_code', 'Contract_year', 'Memo_Location',
    'CompanyName', 'Type_contract_name', 'Start_contract', 'End_contract',
    'Status_contract_Desc', *DETAIL_FIELDS,
)


class SpaceProfileError(ValueError):
    pass


SPACE_FILTER_FIELDS = {
    'business': 'Business_Types_BI',
    'location': 'Memo_Location',
    'area_status': 'Status_Area',
}


def _filter_token(value):
    value = str(value or '').strip()
    return 'value:' + value if value else 'missing'


def space_filter_options(rows):
    options = {}
    for name, column in SPACE_FILTER_FIELDS.items():
        values = {_filter_token(row.get(column)) for row in rows}
        options[name] = [('', 'ทั้งหมด')] + [
            (value, 'ไม่ระบุ' if value == 'missing' else value[6:])
            for value in sorted(values)
        ]
    return options


def filter_space_rows(rows, filters):
    return [row for row in rows if all(
        not filters.get(name) or _filter_token(row.get(column)) == filters[name]
        for name, column in SPACE_FILTER_FIELDS.items()
    )]


def _rows(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _live_rows(cursor, target_date):
    cursor.execute('EXEC dbo.SP_Contract_Location_SubArea_Test @c_date = ?', target_date.strftime('%Y%m%d'))
    rows = _rows(cursor)
    # 0 เป็นค่ากลางระดับพื้นที่ของหน้าจอใหม่นี้ โดยไม่เปลี่ยนคีย์ของตารางเดิม
    # หากยังไม่มีค่ากลาง ใช้รายละเอียดล่าสุดของพื้นที่จากระบบเดิมเป็นค่าเริ่มต้น
    cursor.execute('''
        SELECT SubArea_id, Floor_BI, Shop_Sell_BI, Business_Types_BI,
               Shop_name_BI, Objective_Desc_BI, Updated_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY SubArea_id
                ORDER BY CASE WHEN Contract_id = 0 THEN 0 ELSE 1 END,
                         Updated_at DESC, Contract_id DESC
            ) AS rn
            FROM dbo.Contract_Location_Input
        ) AS details WHERE rn = 1
    ''')
    details = {str(row['SubArea_id']): row for row in _rows(cursor)}
    for row in rows:
        saved = details.get(str(row['SubArea_id']), {})
        row.update({field: saved.get(field) or '' for field in DETAIL_FIELDS})
        row['details_complete'] = all(str(row[field]).strip() for field in DETAIL_FIELDS)
    return rows


def _latest_closed(cursor):
    cursor.execute('SELECT MAX(Snapshot_date) FROM dbo.Contract_Location_Snapshot')
    return cursor.fetchone()[0]


def _active_date(latest):
    if latest:
        year, month = (latest.year + 1, 1) if latest.month == 12 else (latest.year, latest.month + 1)
    else:
        period = settings.SPACE_PROFILE_START_PERIOD
        year, month = int(period[:4]), int(period[4:])
    return date(year, month, calendar.monthrange(year, month)[1])


def get_period_navigation():
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        cursor.execute('''SELECT DISTINCT s.Snapshot_date
            FROM dbo.Contract_Location_Snapshot s
            JOIN dbo.Contract_Location_Period p ON p.Period_date = s.Snapshot_date
            WHERE p.Period_status = 'CLOSED' ORDER BY s.Snapshot_date DESC''')
        closed_dates = [row[0] for row in cursor.fetchall()]
        return _working_date(cursor), closed_dates
    finally:
        conn.close()


def list_space_periods():
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        cursor.execute('''SELECT p.*, COALESCE(s.total_rows, 0) AS total_rows
            FROM dbo.Contract_Location_Period p
            LEFT JOIN (SELECT Snapshot_date, COUNT(*) AS total_rows
                       FROM dbo.Contract_Location_Snapshot GROUP BY Snapshot_date) s
                ON s.Snapshot_date = p.Period_date
            ORDER BY p.Period_date DESC''')
        return _rows(cursor)
    finally:
        conn.close()


def _working_date(cursor):
    # เมื่อเปิดรอบย้อนหลัง ให้ทำรอบเก่าก่อน รอบใหม่ยังคงสถานะ OPEN รอไว้
    cursor.execute("SELECT MIN(Period_date) FROM dbo.Contract_Location_Period WHERE Period_status = 'OPEN'")
    return cursor.fetchone()[0]


def _period_status(cursor, target_date):
    cursor.execute('SELECT Period_status FROM dbo.Contract_Location_Period WHERE Period_date = ?', target_date)
    row = cursor.fetchone()
    if not row:
        raise SpaceProfileError('ไม่พบรอบข้อมูลที่ระบุ')
    return row[0]


def _snapshot_rows(cursor, target_date):
    cursor.execute('SELECT * FROM dbo.Contract_Location_Snapshot WHERE Snapshot_date = ?', target_date)
    return _rows(cursor)


def load_space_period(target_date):
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        status = _period_status(cursor, target_date)
        rows = _snapshot_rows(cursor, target_date)
        if rows:
            return {'rows': rows, 'closed': status == 'CLOSED',
                    'editable': status == 'OPEN' and target_date == _working_date(cursor), 'reopened': status == 'OPEN'}
        if status == 'CLOSED':
            raise SpaceProfileError('รอบปิดแล้วแต่ไม่พบข้อมูลประวัติ กรุณาติดต่อผู้ดูแล')
        if target_date != _working_date(cursor):
            raise SpaceProfileError('เดือนนี้ยังไม่ใช่รอบที่กำลังจัดทำ กรุณากลับไปหน้าจัดทำข้อมูล')
        return {
            'rows': _live_rows(cursor, target_date), 'closed': False,
            'editable': True,
        }
    finally:
        conn.close()


def _lock(cursor):
    # serialize การบันทึก/ปิดรอบจาก CMS เพื่อไม่ให้ปิดรอบพร้อมการแก้ค่าได้
    cursor.execute('''
        SET NOCOUNT ON;
        SET XACT_ABORT ON;
        IF @@TRANCOUNT = 0 BEGIN TRANSACTION;
        DECLARE @result int;
        EXEC @result = sys.sp_getapplock
            @Resource = N'CMS.ContractLocationPeriod', @LockMode = 'Exclusive',
            @LockOwner = 'Transaction', @LockTimeout = 10000;
        SELECT @result;
    ''')
    if cursor.fetchone()[0] < 0:
        raise SpaceProfileError('มีผู้ใช้งานกำลังบันทึกข้อมูล กรุณาลองใหม่')


def _check_open(cursor, target_date):
    if target_date.day != calendar.monthrange(target_date.year, target_date.month)[1]:
        raise SpaceProfileError('รอบข้อมูลต้องเป็นวันสิ้นเดือน')
    if _period_status(cursor, target_date) != 'OPEN':
        raise SpaceProfileError('รอบนี้ปิดแล้ว ไม่สามารถแก้ไขได้')
    if target_date != _working_date(cursor):
        raise SpaceProfileError('บันทึกได้เฉพาะรอบที่กำลังจัดทำ กรุณากลับไปหน้าจัดทำข้อมูล')


def save_space_details(target_date, subarea_id, details, user):
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        _lock(cursor)
        _check_open(cursor, target_date)
        snapshot = _snapshot_rows(cursor, target_date)
        rows = snapshot or _live_rows(cursor, target_date)
        if not any(str(row['SubArea_id']) == subarea_id for row in rows):
            raise SpaceProfileError('ไม่พบพื้นที่ที่เลือกในรอบนี้')
        values = [details[field] for field in DETAIL_FIELDS]
        if any(not str(value).strip() for value in values):
            raise SpaceProfileError('กรุณากรอกรายละเอียดให้ครบทั้ง 5 ช่อง')
        if len(values[0]) > 10 or any(len(value) > 255 for value in values[1:]):
            raise SpaceProfileError('รายละเอียดมีความยาวเกินกำหนด')
        if snapshot:
            # Admin เปิดให้แก้เดือนนี้อย่างชัดเจน: เปลี่ยนเฉพาะ 5 ช่องใน Snapshot เดือนนั้น
            # ไม่อัปเดต Input กลาง จึงไม่เปลี่ยนค่ารอบปัจจุบันหรือเดือนอื่น
            cursor.execute('''UPDATE dbo.Contract_Location_Snapshot
                SET Floor_BI = ?, Shop_Sell_BI = ?, Business_Types_BI = ?,
                    Shop_name_BI = ?, Objective_Desc_BI = ?
                WHERE Snapshot_date = ? AND SubArea_id = ?
            ''', *values, target_date, subarea_id)
            cursor.execute('''UPDATE dbo.Contract_Location_Period
                SET Modified_by = ?, Modified_at = SYSDATETIME()
                WHERE Period_date = ?''', user, target_date)
            conn.commit()
            return
        # Store บันทึกเดิมบังคับตรวจพื้นที่กับ forBI และผูกตามสัญญา
        # จึงใช้ Service บันทึกค่ากลางพื้นที่ลง Input โดยตรงแบบ parameterized
        cursor.execute('''
            UPDATE dbo.Contract_Location_Input WITH (UPDLOCK, HOLDLOCK)
            SET Floor_BI = ?, Shop_Sell_BI = ?, Business_Types_BI = ?,
                Shop_name_BI = ?, Objective_Desc_BI = ?, Updated_by = ?, Updated_at = SYSDATETIME()
            WHERE SubArea_id = ? AND Contract_id = 0
            SELECT @@ROWCOUNT;
        ''', *values, user, subarea_id)
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT dbo.Contract_Location_Input
                    (SubArea_id, Contract_id, Floor_BI, Shop_Sell_BI, Business_Types_BI,
                     Shop_name_BI, Objective_Desc_BI, Updated_by)
                VALUES (?, 0, ?, ?, ?, ?, ?, ?)
            ''', subarea_id, *values, user)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def close_space_period(target_date, user):
    if target_date > date.today():
        raise SpaceProfileError('ยังไม่ถึงวันสิ้นเดือน ไม่สามารถปิดรอบล่วงหน้าได้')
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        _lock(cursor)
        _check_open(cursor, target_date)
        snapshot = _snapshot_rows(cursor, target_date)
        rows = snapshot or _live_rows(cursor, target_date)
        if not rows:
            raise SpaceProfileError('ไม่พบข้อมูลพื้นที่ จึงไม่สามารถปิดรอบได้')
        # ผู้ใช้ยืนยันปิดรอบได้แม้รายละเอียดไม่ครบ เก็บช่องว่างตามจริง
        # โดยไม่เติมค่าแทนหรือแก้ Input เพื่อให้ประวัติสะท้อนข้อมูล ณ เวลาปิดรอบ
        if len({row['SubArea_id'] for row in rows}) != len(rows):
            raise SpaceProfileError('พบรหัสพื้นที่ซ้ำ กรุณาติดต่อผู้ดูแลระบบ')
        # Store ปิดรอบเดิมจับ Input ตามสัญญา จึงประกอบ Snapshot จากค่ากลางพื้นที่
        # ที่อ่านใน transaction นี้ ไม่ลบหรือเขียนทับ Snapshot เก่า
        columns = ', '.join(SNAPSHOT_FIELDS)
        placeholders = ', '.join('?' for _ in range(len(SNAPSHOT_FIELDS) + 2))
        sql = f'INSERT dbo.Contract_Location_Snapshot (Snapshot_date, {columns}, Closed_by) VALUES ({placeholders})'
        if not snapshot:
            for row in rows:
                cursor.execute(sql, target_date, *(row.get(field) for field in SNAPSHOT_FIELDS), user)
        cursor.execute('''UPDATE dbo.Contract_Location_Period
            SET Period_status = 'CLOSED', Closed_by = ?, Closed_at = SYSDATETIME(),
                Modified_by = ?, Modified_at = SYSDATETIME()
            WHERE Period_date = ?''', user, user, target_date)
        # เปิดเดือนถัดไปเฉพาะรอบใหม่ ไม่สร้างรายการซ้ำเมื่อปิดรอบย้อนหลังอีกครั้ง
        next_date = _active_date(target_date)
        cursor.execute('''IF NOT EXISTS (SELECT 1 FROM dbo.Contract_Location_Period WHERE Period_date = ?)
            INSERT dbo.Contract_Location_Period
                (Period_date, Period_status, Opened_by, Opened_at, Modified_by)
            VALUES (?, 'OPEN', ?, SYSDATETIME(), ?)''', next_date, next_date, user, user)
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reopen_space_period(target_date, reason, user):
    reason = (reason or '').strip()
    if not reason or len(reason) > 500:
        raise SpaceProfileError('กรุณาระบุเหตุผลเปิดรอบ 1–500 อักขระ')
    conn = get_db_connection()
    try:
        conn.timeout = 30
        cursor = conn.cursor()
        _lock(cursor)
        if _period_status(cursor, target_date) != 'CLOSED':
            raise SpaceProfileError('รอบนี้เปิดอยู่แล้ว กรุณาโหลดรายการใหม่')
        if not _snapshot_rows(cursor, target_date):
            raise SpaceProfileError('ไม่พบข้อมูลประวัติของเดือนนี้')
        cursor.execute('''UPDATE dbo.Contract_Location_Period
            SET Period_status = 'OPEN', Opened_by = ?, Opened_at = SYSDATETIME(),
                Reopen_reason = ?, Revision_no = Revision_no + 1,
                Modified_by = ?, Modified_at = SYSDATETIME()
            WHERE Period_date = ?''', user, reason, user, target_date)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


