# meters/services.py
import pyodbc
from django.conf import settings
from openpyxl import load_workbook

STATUS_MAP = {
    'สัญญา': '1', 'ต่อสัญญา': '3', 'ไม่ต่อสัญญา': '4',
    'ยกเลิกสัญญา': '5', 'รอปิดสัญญา': '8', 'ปิดสัญญา': '9',
}

COL = {
    'YEAR': 0, 'CUSTOMER_NAME': 2, 'CONTRACT_NO': 4, 'CONTRACT_CODE': 5,
    'LOCATION': 8, 'LOCATION_NAME': 9,
    'AREA': 10, 'AREA_NAME': 11, 'SUBAREA': 12, 'SUBAREA_NAME': 13, 'STATUS': 15,
    'CONFIRM': 16, 'METER_NO': 19,
}
COL_PHASE = 20

DEFAULT_USER = 'web_upload'  # เปลี่ยนเป็น username จริงของผู้ใช้ที่ login ได้ ถ้ามีระบบ login แล้ว


def get_db_connection():
    db = settings.DATABASES['default']
    conn_str = (
        f"DRIVER={{{db['OPTIONS'].get('driver', 'ODBC Driver 17 for SQL Server')}}};"
        f"SERVER={db['HOST']},{db.get('PORT') or '1433'};"
        f"DATABASE={db['NAME']};"
        f"UID={db['USER']};"
        f"PWD={db['PASSWORD']};"
    )
    return pyodbc.connect(conn_str)


def find_subarea(location_id, area_id, subarea_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT Location_id, Area_id, SubArea_id, SubArea_name
            FROM dbo.Contract_location_subarea_ms
            WHERE Location_id = ? AND Area_id = ? AND SubArea_id = ?
            """,
            location_id, area_id, subarea_id,
        )
        return cursor.fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# หาชีท "สัญญา" ของน้ำ/ไฟ แบบเจาะจง -- ต้องขึ้นต้นด้วย "สัญญาปี" และมีคำ keyword
# (น้ำ/ไฟ) อยู่ในชื่อ กันไปจับชีทอื่นที่บังเอิญมีคำว่าน้ำ/ไฟปนอยู่ผิดๆ เช่น
# 'มิเตอร์น้ำ35ตัว' หรือ 'มิเตอร์ไฟฟ้า63ตัว' ซึ่งไม่ใช่ชีทสัญญาและมีคอลัมน์คนละแบบ
# ถ้าเจอมากกว่า 1 ชีทที่เข้าเงื่อนไข ให้ error ทันทีแทนที่จะเดาเอาอันแรก
# ---------------------------------------------------------------------------
def find_contract_sheet(sheetnames, keyword):
    candidates = [n for n in sheetnames if n.startswith('สัญญาปี') and keyword in n]
    if len(candidates) > 1:
        raise ValueError(
            f"พบชีทสัญญาที่ขึ้นต้นด้วย 'สัญญาปี' และมีคำว่า {keyword!r} มากกว่า 1 ชีท: {candidates} "
            f"กรุณาตรวจสอบชื่อชีทในไฟล์ Excel"
        )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# STEP 1: parse ไฟล์ Excel เป็นรายการ "staged" เท่านั้น -- ไม่เขียนข้อมูลลง DB
# ใช้ find_subarea (read-only) เพื่อตรวจสอบล่วงหน้าว่าแถวไหนจะ error ตอนบันทึกจริง
# ---------------------------------------------------------------------------
def parse_excel_staged(uploaded_file):
    wb = load_workbook(uploaded_file, data_only=True)
    water_sheet = find_contract_sheet(wb.sheetnames, 'น้ำ')
    elec_sheet = find_contract_sheet(wb.sheetnames, 'ไฟ')

    rows_out = []
    counter = {'idx': 0}

    def handle_sheet(sheet_name, type_cd):
        if not sheet_name:
            return
        type_label = 'น้ำ' if type_cd == 9 else 'ไฟฟ้า'
        for row in wb[sheet_name].iter_rows(min_row=2, values_only=True):
            if not row or len(row) <= max(COL.values()):
                continue

            subarea_id, loc_id, area_id = row[COL['SUBAREA']], row[COL['LOCATION']], row[COL['AREA']]
            if not subarea_id or not loc_id or not area_id:
                continue
            loc_id, area_id, subarea_id = str(loc_id), str(area_id), str(subarea_id)

            contract_id = row[COL['CONTRACT_NO']]
            contract_code = row[COL['CONTRACT_CODE']]
            confirm_flag = row[COL['CONFIRM']]
            meter_no_raw = row[COL['METER_NO']]

            counter['idx'] += 1
            entry = {
                'idx': counter['idx'],
                'type_cd': type_cd, 'type_label': type_label,
                'contract_year': row[COL['YEAR']],
                'customer_name': row[COL['CUSTOMER_NAME']],
                'location_id': loc_id, 'area_id': area_id,
                'subarea_id': subarea_id, 'subarea_name': row[COL['SUBAREA_NAME']],
                'contract_id': contract_id, 'contract_code': contract_code,
                'meter_no': None, 'meter_no_status': None, 'phase_type': None,
                'status': 'ok', 'message': '',
            }

            if confirm_flag != 1 or meter_no_raw == 'ไม่มีมิเตอร์':
                entry['status'] = 'skip'
                entry['message'] = f'ไม่มีการคิดค่า{type_label}ในพื้นที่นี้'
                rows_out.append(entry)
                continue

            if not find_subarea(loc_id, area_id, subarea_id):
                entry['status'] = 'error'
                entry['message'] = f'ไม่พบพื้นที่ {loc_id}/{area_id}/{subarea_id} ในฐานข้อมูล'
                rows_out.append(entry)
                continue

            if not contract_code:
                entry['status'] = 'error'
                entry['message'] = 'ไม่พบรหัสสัญญาในแถวนี้'
                rows_out.append(entry)
                continue

            meter_no = None if meter_no_raw in (None, 'มิเตอร์ไม่มีเลข (GEN เลข)') else str(meter_no_raw)
            entry['meter_no'] = meter_no
            entry['meter_no_status'] = 'รอ Gen เลข' if meter_no is None else 'ปกติ'

            if type_cd == 8 and len(row) > COL_PHASE and row[COL_PHASE]:
                entry['phase_type'] = '3เฟส' if '3' in str(row[COL_PHASE]) else '1เฟส'

            rows_out.append(entry)

    handle_sheet(water_sheet, 9)
    handle_sheet(elec_sheet, 8)

    summary = {
        'total': len(rows_out),
        'ok': sum(1 for r in rows_out if r['status'] == 'ok'),
        'skip': sum(1 for r in rows_out if r['status'] == 'skip'),
        'error': sum(1 for r in rows_out if r['status'] == 'error'),
    }

    return {
        'rows': rows_out,
        'summary': summary,
        'water_sheet_found': bool(water_sheet),
        'elec_sheet_found': bool(elec_sheet),
    }


# ---------------------------------------------------------------------------
# STEP 3: เขียนข้อมูลจริงลง DB (เรียก stored procedure) เฉพาะตอนกด "ยืนยันนำเข้า"
# ---------------------------------------------------------------------------
def sp_meter_save(cursor, location_id, area_id, subarea_id, type_cd, meter_no,
                   meter_no_status, user_id, logs, phase_type=None):
    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_Save
            @Location_id     = ?,
            @Area_id         = ?,
            @SubArea_id      = ?,
            @Meter_type_cd   = ?,
            @Meter_no        = ?,
            @Meter_no_status = ?,
            @Phase_type      = ?,
            @UserId          = ?
        """,
        location_id, area_id, subarea_id, type_cd, meter_no, meter_no_status, phase_type, user_id
    )
    row = cursor.fetchone()
    meter_id = row[0] if row else None
    cls = 'water' if type_cd == 9 else 'electric'
    logs.append((cls, f"EXEC sp_Contract_Meter_Save  @SubArea_id='{subarea_id}', "
                       f"@Meter_type_cd={type_cd}, @Meter_no={meter_no!r}  -> Meter_id={meter_id}"))
    return meter_id


def sp_bind_to_contract(cursor, contract_code, location_id, area_id, subarea_id, meter_id, user_id, logs):
    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_BindToContract
            @Contract_code = ?,
            @Location_id   = ?,
            @Area_id       = ?,
            @SubArea_id    = ?,
            @Meter_id_list = ?,
            @UserId        = ?
        """,
        contract_code, location_id, area_id, subarea_id, str(meter_id), user_id
    )
    logs.append(('bind', f"EXEC sp_Contract_Meter_BindToContract  @Contract_code='{contract_code}', "
                          f"@Meter_id_list='{meter_id}'"))


def commit_staged_rows(rows, user_id):
    """
    รับ rows ที่ parse+ตรวจสอบแล้วจาก parse_excel_staged (เก็บอยู่ใน session)
    วนเรียก SP จริงเฉพาะแถวที่ status == 'ok' เท่านั้น
    คืนค่า logs / stats / rows (แนบ final_status ต่อแถว ใช้แสดงหน้า step4)
    """
    logs = []
    stats = {'meter_ok': 0, 'skipped': 0, 'errors': 0}
    result_rows = []

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for r in rows:
            row_result = dict(r)

            if r['status'] == 'skip':
                logs.append(('skip', f"SKIP  SubArea={r['subarea_id']} สัญญา {r['contract_code'] or '-'} -- {r['message']}"))
                stats['skipped'] += 1
                row_result['final_status'] = 'skip'
                result_rows.append(row_result)
                continue

            if r['status'] == 'error':
                logs.append(('err', f"ERROR  SubArea={r['subarea_id']} -- {r['message']}"))
                stats['errors'] += 1
                row_result['final_status'] = 'error'
                result_rows.append(row_result)
                continue

            try:
                meter_id = sp_meter_save(
                    cursor, r['location_id'], r['area_id'], r['subarea_id'], r['type_cd'],
                    r['meter_no'], r['meter_no_status'], user_id, logs, r.get('phase_type'),
                )
                stats['meter_ok'] += 1
                row_result['meter_id'] = meter_id
                row_result['final_status'] = 'success'

                if r['contract_code'] and meter_id:
                    sp_bind_to_contract(
                        cursor, r['contract_code'], r['location_id'], r['area_id'],
                        r['subarea_id'], meter_id, user_id, logs,
                    )
            except Exception as exc:
                logs.append(('err', f"ERROR  SubArea={r['subarea_id']} -- {exc}"))
                stats['errors'] += 1
                row_result['final_status'] = 'error'
                row_result['message'] = str(exc)

            result_rows.append(row_result)

        conn.commit()
    finally:
        conn.close()

    return {'logs': logs, 'stats': stats, 'rows': result_rows}


# ---------------------------------------------------------------------------
# Dashboard (อ่านอย่างเดียว)
# ---------------------------------------------------------------------------
def fetch_subareas():
    """
    ตารางรวมสำหรับหน้า dashboard -- เริ่มจาก Contract_meter_ms (ทะเบียนมิเตอร์) เป็นหลัก
    แล้ว LEFT JOIN ออกไปหาสัญญาที่ผูกอยู่ (ถ้ามี) เพื่อให้ "มิเตอร์ที่ยังไม่ถูกผูกกับสัญญาไหนเลย"
    ยังโผล่ในตาราง (เป็นแถว Pending) แทนที่จะหายไปเงียบๆ แบบตอนใช้ INNER JOIN จาก Contract_meter_tr
    ก่อนหน้านี้ -- ทำให้ตัวเลขรวมในตารางตรงกับตัวเลขสถิติที่การ์ดด้านบน (fetch_dashboard_stats)
    ซึ่งนับจากทะเบียนมิเตอร์ทั้งหมดเหมือนกัน

    ถ้าต้องการรายละเอียดของสัญญาเดียว ให้ใช้ fetch_contract_meter_detail() แทน (เรียก SP ตรงๆ)

    หมายเหตุ: ยังไม่มีคอลัมน์ชื่อลูกหนี้ ต้องหาจากตารางลูกค้าแยก (เช่น Contract_Customer_SAP_ms)
    เพิ่มทีหลังถ้าต้องการโชว์ชื่อลูกหนี้ในตาราง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.Location_id,
                m.Area_id,
                m.SubArea_id,
                s.SubArea_name,
                MAX(CASE WHEN m.Meter_type_cd = 9 THEN m.Meter_no END) AS water_meter_no,
                MAX(CASE WHEN m.Meter_type_cd = 8 THEN m.Meter_no END) AS electric_meter_no,
                MAX(c.Contract_code) AS contract_code
            FROM Contract_meter_ms m
            LEFT JOIN Contract_location_subarea_ms s ON s.SubArea_id = m.SubArea_id
            LEFT JOIN Contract_meter_tr t ON t.Meter_id = m.Meter_id AND t.UseOrNot = 1
            LEFT JOIN Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            GROUP BY m.Location_id, m.Area_id, m.SubArea_id, s.SubArea_name
            ORDER BY m.Location_id, m.Area_id, m.SubArea_id
        """)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_contract_meter_detail(contract_id=None, contract_code=None):
    """
    หน้ารายละเอียดของสัญญาเดียว -- เรียก sp_Contract_Meter_SelectByContract ตรงๆ
    ตามเจตนาเดิมของ SP (ดึงทีละสัญญา ไม่ใช้กับหน้า dashboard ที่โชว์ทุกสัญญาพร้อมกัน)
    ระบุ contract_id หรือ contract_code อย่างใดอย่างหนึ่ง
    """
    if contract_id is None and contract_code is None:
        raise ValueError('ต้องระบุ contract_id หรือ contract_code อย่างใดอย่างหนึ่ง')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "EXEC dbo.sp_Contract_Meter_SelectByContract @Contract_id = ?, @Contract_code = ?",
            contract_id, contract_code,
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_meters(type_filter=None, search=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT
                m.Meter_id, m.SubArea_id, m.Meter_type_cd,
                m.Meter_no, m.Meter_no_status,
                STRING_AGG(c.Contract_code, ', ') AS bound_contracts
            FROM Contract_meter_ms m
            LEFT JOIN Contract_meter_tr t ON t.Meter_id = m.Meter_id
            LEFT JOIN Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            WHERE 1=1
        """
        params = []
        if type_filter in ('8', '9'):
            sql += " AND m.Meter_type_cd = ?"
            params.append(int(type_filter))
        if search:
            sql += """ AND (
                m.SubArea_id LIKE ? OR
                m.Meter_no LIKE ? OR
                EXISTS (
                    SELECT 1 FROM Contract_meter_tr t2
                    JOIN Contract_hrd_tr c2 ON c2.Contract_id = t2.Contract_id
                    WHERE t2.Meter_id = m.Meter_id AND c2.Contract_code LIKE ?
                )
            )"""
            like = f"%{search}%"
            params += [like, like, like]
        sql += " GROUP BY m.Meter_id, m.SubArea_id, m.Meter_type_cd, m.Meter_no, m.Meter_no_status"
        sql += " ORDER BY m.Meter_id DESC"

        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for r in rows:
            r['bound_contracts'] = (r['bound_contracts'] or '').split(', ') if r['bound_contracts'] else []
        return rows
    finally:
        conn.close()


def fetch_dashboard_stats():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM Contract_location_subarea_ms) AS subarea_count,
                (SELECT COUNT(DISTINCT Contract_id) FROM Contract_meter_tr) AS contract_count,
                (SELECT COUNT(*) FROM Contract_meter_ms WHERE Meter_type_cd = 9) AS water_count,
                (SELECT COUNT(*) FROM Contract_meter_ms WHERE Meter_type_cd = 8) AS electric_count,
                (SELECT COUNT(*) FROM Contract_meter_ms WHERE Meter_no_status = N'รอ Gen เลข') AS pending_gen
        """)
        columns = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else {}
    finally:
        conn.close()