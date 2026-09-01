# meters/services.py
import pyodbc
from django.conf import settings
from openpyxl import load_workbook

STATUS_MAP = {
    'สัญญา': '1', 'ต่อสัญญา': '3', 'ไม่ต่อสัญญา': '4',
    'ยกเลิกสัญญา': '5', 'รอปิดสัญญา': '8', 'ปิดสัญญา': '9',
}

COL_KEYS = {
    'YEAR': ['ปีที่สร้างสัญญา'],
    'CUSTOMER_NAME': ['ชื่อลูกหนี้'],
    'TAX_ID': ['เลข13หลัก'],
    'CONTRACT_NO': ['เลขที่สัญญา'],
    'CONTRACT_CODE': ['รหัสสัญญา'],
    'LOCATION': ['Location_id'],       # อาจไม่มีในบางไฟล์ -- ต้องเช็ค None ก่อนใช้
    'LOCATION_NAME': ['สถานที่ตั้ง'],
    'AREA': ['Area_id'],
    'AREA_NAME': ['พื้นที่ตามที่ตั้งพื้นที่เช่า'],
    'SUBAREA': ['SubArea_id'],
    'SUBAREA_NAME': ['พื้นที่ย่อยตามที่ตั้งพื้นที่เช่า'],
    'STATUS': ['สถานะสัญญา'],
    'CONFIRM': ['ยืนยันพื้นที่ที่คิดค่า'],
    'METER_NO': ['เลขประจำเครื่องวัด'],
    'PHASE': ['ระบบไฟฟ้า'],
}

DEFAULT_USER = 'web_upload'


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


def build_column_map(header_row):
    col_map = {}
    for field, keywords in COL_KEYS.items():
        for i, header in enumerate(header_row):
            if header and all(kw in str(header) for kw in keywords):
                col_map[field] = i
                break
    return col_map


def find_subarea(area_id, subarea_id, location_id=None):
    """
    หาพื้นที่ในฐานข้อมูล คืนค่าเป็น row (Location_id, Area_id, SubArea_id, SubArea_name)
    หรือ None -- เวลาไม่มี location_id ส่งเข้ามา ต้องเอา Location_id จาก row ที่เจอนี้ไปใช้ต่อ
    ตอนบันทึกจริง (sp_Contract_Meter_Save ต้องการ @Location_id แบบ NOT NULL เสมอ)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if location_id:
            cursor.execute(
                """
                SELECT Location_id, Area_id, SubArea_id, SubArea_name
                FROM dbo.Contract_location_subarea_ms
                WHERE Location_id = ? AND Area_id = ? AND SubArea_id = ?
                """,
                location_id, area_id, subarea_id,
            )
        else:
            cursor.execute(
                """
                SELECT Location_id, Area_id, SubArea_id, SubArea_name
                FROM dbo.Contract_location_subarea_ms
                WHERE Area_id = ? AND SubArea_id = ?
                """,
                area_id, subarea_id,
            )
        return cursor.fetchone()
    finally:
        conn.close()


def find_contract_by_code(contract_code):
    """
    เช็คว่ารหัสสัญญานี้มีอยู่จริงใน Contract_hrd_tr หรือไม่ (ก่อนหน้านี้ parse_excel_staged
    เช็คแค่ว่า contract_code ไม่ว่างเปล่า ไม่เคยเช็คว่ามีอยู่จริงในระบบเลย ทำให้รหัสสัญญาที่
    พิมพ์ผิด/ยังไม่ได้สร้าง หลุดผ่าน step 2 ไปเป็น 'ok' แล้วเพิ่ง error ตอน commit จริงแทน)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Contract_id, Contract_code FROM dbo.Contract_hrd_tr WHERE Contract_code = ?",
            contract_code,
        )
        return cursor.fetchone()
    finally:
        conn.close()


def find_contract_sheet(sheetnames, keyword):
    candidates = [n for n in sheetnames if n.startswith('สัญญาปี') and keyword in n]
    if len(candidates) > 1:
        raise ValueError(
            f"พบชีทสัญญาที่ขึ้นต้นด้วย 'สัญญาปี' และมีคำว่า {keyword!r} มากกว่า 1 ชีท: {candidates} "
            f"กรุณาตรวจสอบชื่อชีทในไฟล์ Excel"
        )
    return candidates[0] if candidates else None


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

        ws = wb[sheet_name]
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        col = build_column_map(header_row)

        required = ['SUBAREA', 'AREA', 'CONTRACT_NO', 'CONTRACT_CODE', 'CONFIRM', 'METER_NO']
        missing = [f for f in required if f not in col]
        if missing:
            raise ValueError(
                f"ชีท '{sheet_name}' หาคอลัมน์ไม่เจอ: {missing} "
                f"กรุณาตรวจสอบชื่อ header แถวแรกของชีทนี้"
            )
        has_location = 'LOCATION' in col

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row:
                continue

            subarea_id = row[col['SUBAREA']]
            area_id = row[col['AREA']]
            loc_id = row[col['LOCATION']] if has_location else None
            if not subarea_id or not area_id:
                continue
            area_id, subarea_id = str(area_id), str(subarea_id)
            loc_id = str(loc_id) if loc_id else None

            contract_id = row[col['CONTRACT_NO']]
            contract_code = row[col['CONTRACT_CODE']]
            confirm_flag = row[col['CONFIRM']]
            meter_no_raw = row[col['METER_NO']]

            counter['idx'] += 1
            entry = {
                'idx': counter['idx'],
                'type_cd': type_cd, 'type_label': type_label,
                'contract_year': row[col['YEAR']] if 'YEAR' in col else None,
                'customer_name': row[col['CUSTOMER_NAME']] if 'CUSTOMER_NAME' in col else None,
                'tax_id': row[col['TAX_ID']] if 'TAX_ID' in col else None,
                'location_id': loc_id, 'area_id': area_id,
                'subarea_id': subarea_id,
                'subarea_name': row[col['SUBAREA_NAME']] if 'SUBAREA_NAME' in col else None,
                'contract_id': contract_id, 'contract_code': contract_code,
                'meter_no': None, 'meter_no_status': None, 'phase_type': None,
                'status': 'ok', 'message': '',
            }

            if confirm_flag != 1 or meter_no_raw == 'ไม่มีมิเตอร์':
                entry['status'] = 'skip'
                entry['message'] = f'ไม่มีการคิดค่า{type_label}ในพื้นที่นี้'
                rows_out.append(entry)
                continue

            # --- เช็คพื้นที่ + แก้บั๊ก Location_id เป็น None ---
            subarea_match = find_subarea(area_id, subarea_id, loc_id)
            if not subarea_match:
                where = f'{loc_id}/{area_id}/{subarea_id}' if loc_id else f'{area_id}/{subarea_id}'
                entry['status'] = 'error'
                entry['message'] = f'ไม่พบพื้นที่ {where} ในฐานข้อมูล'
                rows_out.append(entry)
                continue

            if not loc_id:
                loc_id = str(subarea_match[0])
                entry['location_id'] = loc_id

            # อ่านเลขมิเตอร์/เฟสจากไฟล์ก่อนเสมอ ไม่ว่าจะเช็ครหัสสัญญาผ่านหรือไม่
            # (แถวไหน error ก็ยังเห็นข้อมูลจริงจากไฟล์ในตาราง review ได้ ไม่ใช่ว่างเปล่า)
            meter_no = None if meter_no_raw in (None, 'มิเตอร์ไม่มีเลข (GEN เลข)') else str(meter_no_raw)
            entry['meter_no'] = meter_no
            entry['meter_no_status'] = 'รอ Gen เลข' if meter_no is None else 'ปกติ'
            if type_cd == 8 and 'PHASE' in col and row[col['PHASE']]:
                entry['phase_type'] = '3เฟส' if '3' in str(row[col['PHASE']]) else '1เฟส'

            # --- เช็ครหัสสัญญาต้องมีอยู่จริงในระบบ (ของเดิมเช็คแค่ไม่ว่างเปล่า) ---
            if not contract_code:
                entry['status'] = 'error'
                entry['message'] = 'ไม่พบรหัสสัญญาในแถวนี้'
                rows_out.append(entry)
                continue

            if not find_contract_by_code(contract_code):
                entry['status'] = 'error'
                entry['message'] = f"ไม่พบรหัสสัญญา '{contract_code}' ในระบบ"
                rows_out.append(entry)
                continue

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
    meter_id = int(row[0]) if row else None
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


def fetch_subareas():
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