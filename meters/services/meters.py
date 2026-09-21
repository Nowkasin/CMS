from .db import get_db_connection

DEFAULT_USER = 'web_upload'


def sp_meter_save(cursor, location_id, area_id, subarea_id, type_cd, meter_no,
                   meter_no_status, user_id, logs, phase_type=None, meter_id=None,
                   meter_remark=None, use_or_not=1):
    """
    meter_id=None (ค่าเริ่มต้น) -> SP จะ INSERT มิเตอร์ใหม่ (ใช้ตอน import จากไฟล์ Excel)
    meter_id=<เลขจริง> -> SP จะ UPDATE มิเตอร์ตัวนั้นแทน (ใช้ตอนแก้ไขจากหน้า dashboard)

    use_or_not (default 1 = เปิดใช้งาน) -- ส่งต่อไป @UseOrNot ของ SP ตรงๆ ผู้เรียกเดิมที่ไม่ส่ง
    พารามิเตอร์นี้ยังทำงานเหมือนเดิมทุกอย่าง (SP มี default @UseOrNot = 1 อยู่แล้ว)
    """
    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_Save
            @Meter_id        = ?,
            @Location_id     = ?,
            @Area_id         = ?,
            @SubArea_id      = ?,
            @Meter_type_cd   = ?,
            @Meter_no        = ?,
            @Meter_no_status = ?,
            @Phase_type      = ?,
            @Meter_remark    = ?,
            @UseOrNot        = ?,
            @UserId          = ?
        """,
        meter_id, location_id, area_id, subarea_id, type_cd, meter_no, meter_no_status,
        phase_type, meter_remark, use_or_not, user_id
    )
    row = cursor.fetchone()
    result_meter_id = int(row[0]) if row else meter_id
    cls = 'water' if type_cd == 9 else 'electric'
    action = 'UPDATE' if meter_id else 'INSERT'
    logs.append((cls, f"EXEC sp_Contract_Meter_Save ({action})  @SubArea_id='{subarea_id}', "
                       f"@Meter_type_cd={type_cd}, @Meter_no={meter_no!r}  -> Meter_id={result_meter_id}"))
    return result_meter_id


def sp_bind_to_contract(cursor, contract_id, location_id, area_id, subarea_id, meter_id, user_id, logs):
   
    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_BindToContract
            @Contract_id   = ?,
            @Location_id   = ?,
            @Area_id       = ?,
            @SubArea_id    = ?,
            @Meter_id_list = ?,
            @UserId        = ?
        """,
        contract_id, location_id, area_id, subarea_id, str(meter_id), user_id
    )
    logs.append(('bind', f"EXEC sp_Contract_Meter_BindToContract  @Contract_id={contract_id}, "
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

                if r.get('db_contract_id') and meter_id:
                    sp_bind_to_contract(
                        cursor, r['db_contract_id'], r['location_id'], r['area_id'],
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


def _to_sql_like_pattern(search):
    """
    แปลงคำค้นแบบที่คนคุ้นเคย (Excel/Windows) เป็น SQL LIKE pattern:
      ?  -> ตัวอักษรใดก็ได้ 1 ตัว   (SQL: _)
      *  -> ตัวอักษรใดก็ได้ 0 ตัวขึ้นไป (SQL: %)
    ต้อง escape % และ _ ตัวจริงที่ผู้ใช้พิมพ์มาก่อน ไม่งั้นถ้าเลขสัญญามี % หรือ _ อยู่จริง
    จะถูกตีความเป็น wildcard ของ SQL ไปโดยไม่ตั้งใจ
    """
    escaped = search.replace('[', '[[]').replace('%', '[%]').replace('_', '[_]')
    escaped = escaped.replace('?', '_').replace('*', '%')
    return f"%{escaped}%"


def fetch_subareas(search=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT
                m.Location_id,
                m.Area_id,
                m.SubArea_id,
                s.SubArea_name,
                MAX(CASE WHEN m.Meter_type_cd = 9 THEN m.Meter_no END) AS water_meter_no,
                MAX(CASE WHEN m.Meter_type_cd = 8 THEN m.Meter_no END) AS electric_meter_no,
                MAX(c.Contract_code) AS contract_code,
                MAX(cu.Customer_id) AS customer_id,
                MAX(cu.CompanyName) AS customer_name
            FROM Contract_meter_ms m
            LEFT JOIN Contract_location_subarea_ms s ON s.SubArea_id = m.SubArea_id
            LEFT JOIN Contract_meter_tr t ON t.Meter_id = m.Meter_id AND t.UseOrNot = 1
            LEFT JOIN Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            LEFT JOIN Contract_customer_tr cu ON cu.Contract_id = c.Contract_id
            GROUP BY m.Location_id, m.Area_id, m.SubArea_id, s.SubArea_name
        """
        params = []
        if search:
            sql += " HAVING MAX(c.Contract_code) LIKE ? ESCAPE '['"
            params.append(_to_sql_like_pattern(search))
        sql += " ORDER BY m.Location_id, m.Area_id, m.SubArea_id"

        cursor.execute(sql, params)
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


def fetch_subarea_meters(subarea_id):
    """
    ดึงข้อมูลพื้นที่ + มิเตอร์น้ำ/ไฟที่มีอยู่ (ถ้ามี) """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.Location_id, s.Area_id, s.SubArea_id, s.SubArea_name,
                   a.Area_name, l.Location_name
            FROM dbo.Contract_location_subarea_ms s
            LEFT JOIN dbo.Contract_location_area_ms a ON a.Area_id = s.Area_id
            LEFT JOIN dbo.Contract_location_ms l ON l.Location_id = s.Location_id
            WHERE s.SubArea_id = ?
            """,
            subarea_id,
        )
        subarea_row = cursor.fetchone()
        if not subarea_row:
            return None
        columns = [c[0] for c in cursor.description]
        result = dict(zip(columns, subarea_row))

        cursor.execute(
            """
            SELECT Meter_id, Meter_type_cd, Meter_no, Meter_no_status, Phase_type
            FROM dbo.Contract_meter_ms
            WHERE SubArea_id = ? AND UseOrNot = 1
            """,
            subarea_id,
        )
        columns2 = [c[0] for c in cursor.description]
        meters = [dict(zip(columns2, r)) for r in cursor.fetchall()]
        result['water'] = next((m for m in meters if m['Meter_type_cd'] == 9), None)
        result['electric'] = next((m for m in meters if m['Meter_type_cd'] == 8), None)

        # ยืนยันจาก schema จริงแล้ว: ตาราง Contract_hrd_tr ไม่มีคอลัมน์ "เลขที่สัญญา" แยกต่างหาก
        # (มีแค่ Contract_id ซึ่งเป็น PK, int กับ Contract_code) -- "เลขที่สัญญา" ที่ผู้ใช้กรอกใน
        # Excel ตอน import (ดู parse_excel_staged/CONTRACT_NO) หมายถึง Contract_id ตัวนี้เอง
        cursor.execute(
            """
            SELECT TOP 1 c.Contract_code, c.Contract_id, cu.Customer_id, cu.CompanyName
            FROM dbo.Contract_meter_tr t
            JOIN dbo.Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            LEFT JOIN dbo.Contract_customer_tr cu ON cu.Contract_id = c.Contract_id
            WHERE t.SubArea_id = ? AND t.UseOrNot = 1
            """,
            subarea_id,
        )
        contract_row = cursor.fetchone()
        if contract_row:
            result['contract_code'] = contract_row[0]
            result['contract_no'] = contract_row[1]
            result['customer_id'] = contract_row[2]
            result['customer_name'] = contract_row[3]
        else:
            result['contract_code'] = None
            result['contract_no'] = None
            result['customer_id'] = None
            result['customer_name'] = None

        return result
    finally:
        conn.close()


def save_subarea_meters(location_id, area_id, subarea_id, user_id,
                         water_enabled, water_meter_id, water_meter_no,
                         electric_enabled, electric_meter_id, electric_meter_no, electric_phase):
    """
    บันทึกมิเตอร์น้ำ/ไฟของ SubArea นี้จากหน้าแก้ไขใน dashboard -- update ทันที (ไม่มีหน้ายืนยันเพิ่ม)
    ถ้ามี *_meter_id อยู่แล้ว (เคยมีมิเตอร์ประเภทนี้อยู่ก่อน) จะเป็นการ UPDATE ตัวเดิม
    ถ้ายังไม่มี (*_meter_id เป็น None) จะเป็นการ INSERT มิเตอร์ใหม่ให้พื้นที่นี้

    คืนค่า (logs, result_meter_ids) โดย result_meter_ids = {'water': <meter_id หรือ None>, 'electric': <meter_id หรือ None>}
    -- ต้องคืน meter_id กลับไปด้วย เพราะถ้าเพิ่งมีการ INSERT มิเตอร์ใหม่ (ไม่เคยมี water_meter_id/electric_meter_id
    มาก่อน) ผู้เรียกจะไม่รู้เลขนั้นเลยถ้าไม่ส่งกลับมา แล้วจะเอาไปบันทึกเลขอ่านมิเตอร์ต่อให้ถูกตัวไม่ได้
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        logs = []
        result_meter_ids = {'water': None, 'electric': None}

        if water_enabled:
            meter_no_status = 'รอ Gen เลข' if not water_meter_no else 'ปกติ'
            result_meter_ids['water'] = sp_meter_save(
                cursor, location_id, area_id, subarea_id, 9, water_meter_no or None,
                meter_no_status, user_id, logs, phase_type=None, meter_id=water_meter_id,
            )

        if electric_enabled:
            meter_no_status = 'รอ Gen เลข' if not electric_meter_no else 'ปกติ'
            result_meter_ids['electric'] = sp_meter_save(
                cursor, location_id, area_id, subarea_id, 8, electric_meter_no or None,
                meter_no_status, user_id, logs, phase_type=electric_phase, meter_id=electric_meter_id,
            )

        conn.commit()
        return logs, result_meter_ids
    finally:
        conn.close()


def fetch_readings_for_meters(meter_ids, billing_year_be, billing_month):
    """
    ดึงเลขอ่านก่อน-หลังของมิเตอร์หลายตัว (ระบุเป็น list) ในรอบบิลหนึ่งๆ
    คืนค่าเป็น dict {meter_id: {'Reading_before':.., 'Reading_after':..}}
    ดึงจาก Contract_Installment_tr_dt โดยจับคู่ Contract_meter_id + เดือน-ปีของ
    Contract_effective_date (แปลง billing_year_be พ.ศ. -> ค.ศ. ก่อนเทียบ)
    """
    meter_ids = [str(m) for m in meter_ids if m]
    if not meter_ids:
        return {}

    ad_year = billing_year_be - 543

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in meter_ids)
        cursor.execute(
            f"""
            SELECT Contract_meter_id, Contract_read_number_before, Contract_read_number_after
            FROM dbo.Contract_Installment_tr_dt
            WHERE YEAR(Contract_effective_date) = ?
              AND MONTH(Contract_effective_date) = ?
              AND Contract_meter_id IN ({placeholders})
            """,
            ad_year, billing_month, *meter_ids,
        )
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

        result = {}
        for r in rows:
            # key คืนเป็น int กลับ ให้ตรงกับ Meter_id (int) ที่ view ใช้ lookup ต่อ
            result[int(r['Contract_meter_id'])] = {
                'Reading_before': r['Contract_read_number_before'],
                'Reading_after': r['Contract_read_number_after'],
            }
        return result
    finally:
        conn.close()


def fetch_meters(type_filter=None, search=None, status_filter='active'):
    """
    status_filter: 'active' (default, UseOrNot=1), 'inactive' (UseOrNot=0), 'all' (ไม่กรอง)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT
                m.Meter_id, m.SubArea_id, m.Meter_type_cd,
                m.Meter_no, m.Meter_no_status, m.UseOrNot,
                STRING_AGG(c.Contract_code, ', ') AS bound_contracts
            FROM Contract_meter_ms m
            LEFT JOIN Contract_meter_tr t ON t.Meter_id = m.Meter_id
            LEFT JOIN Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            WHERE 1=1
        """
        params = []
        if status_filter == 'active':
            sql += " AND m.UseOrNot = 1"
        elif status_filter == 'inactive':
            sql += " AND m.UseOrNot = 0"
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
        sql += " GROUP BY m.Meter_id, m.SubArea_id, m.Meter_type_cd, m.Meter_no, m.Meter_no_status, m.UseOrNot"
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


def save_meter_reading(meter_id, billing_year_be, billing_month, reading_before, reading_after, user_id):
    """
    บันทึกเลขอ่านก่อน-หลังของมิเตอร์ 1 ตัว ในรอบบิลหนึ่ง (UPDATE เท่านั้น)
    คืนค่าจำนวนแถวที่อัปเดตสำเร็จ (0 = ไม่พบแถวงวดนี้)

    สำคัญ: cast meter_id เป็น str() ก่อนส่งเข้า SQL เสมอ -- ดู docstring ของ
    fetch_readings_for_meters เรื่อง data type precedence กับข้อมูลขยะในคอลัมน์นี้
    """
    if reading_before is not None and not isinstance(reading_before, int):
        raise ValueError(f"reading_before ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_before!r}")
    if reading_after is not None and not isinstance(reading_after, int):
        raise ValueError(f"reading_after ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_after!r}")

    ad_year = billing_year_be - 543

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.Contract_Installment_tr_dt
            SET Contract_read_number_before = ?,
                Contract_read_number_after  = ?,
                UserUpdate = ?,
                DateUpdate = GETDATE()
            WHERE Contract_meter_id = ?
              AND YEAR(Contract_effective_date) = ?
              AND MONTH(Contract_effective_date) = ?
            """,
            reading_before, reading_after, user_id, str(meter_id), ad_year, billing_month,
        )
        rows_updated = cursor.rowcount
        conn.commit()
        return rows_updated
    finally:
        conn.close()


def fetch_meter_by_id(meter_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.Meter_id, m.Location_id, m.Area_id, m.SubArea_id, m.Meter_type_cd,
                   m.Meter_no, m.Meter_no_status, m.Phase_type, m.Meter_remark, m.UseOrNot,
                   s.SubArea_name
            FROM dbo.Contract_meter_ms m
            LEFT JOIN dbo.Contract_location_subarea_ms s ON s.SubArea_id = m.SubArea_id
            WHERE m.Meter_id = ?
            """,
            meter_id,
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [c[0] for c in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def save_standalone_meter(subarea_id, meter_type_cd, meter_no, phase_type, user_id, meter_id=None,meter_remark=None, use_or_not=1):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT Location_id, Area_id FROM dbo.Contract_location_subarea_ms WHERE SubArea_id = ?",
            subarea_id,
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"ไม่พบ SubArea_id '{subarea_id}' ในระบบ")
        location_id, area_id = row[0], row[1]

        meter_no_status = 'รอ Gen เลข' if not meter_no else 'ปกติ'
        logs = []
        result_meter_id = sp_meter_save(
            cursor, location_id, area_id, subarea_id, meter_type_cd, meter_no or None,
            meter_no_status, user_id, logs, phase_type=phase_type, meter_id=meter_id,
            meter_remark=meter_remark, use_or_not=use_or_not,
        )
        conn.commit()
        return result_meter_id
    finally:
        conn.close()