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


def find_existing_meter(cursor, subarea_id, meter_type_cd, meter_no):
    """
    หามิเตอร์ที่ลงทะเบียนไว้แล้วในพื้นที่นี้ เพื่อใช้ Meter_id เดิมซ้ำแทนการสร้างแถวใหม่
    คืนค่า (Meter_id, Meter_no, Meter_no_status) หรือ None ถ้าไม่เจอ

    ทำไมต้องมี: sp_Contract_Meter_Save จะ INSERT ใหม่ทุกครั้งที่ @Meter_id เป็น NULL
    โดยไม่เช็คเลยว่าเลขเครื่องวัดนี้มีอยู่แล้วหรือยัง และ UQ_Contract_meter_ms ที่มีอยู่
    คุมแค่ (SubArea_id, Meter_type_cd, Meter_seq) ซึ่ง SP รันเลข seq ใหม่ให้ทุกครั้ง
    -> ไม่มีอะไรกันการซ้ำเลย อัปโหลดไฟล์เดิมซ้ำจึงได้มิเตอร์งอกเพิ่มทั้งชุด
    ผู้เรียกต้องหา Meter_id เดิมเองแล้วส่งเข้า SP เพื่อให้เข้า branch UPDATE

    การจับคู่:
      - มีเลขเครื่องวัด -> เทียบ (SubArea_id, Meter_type_cd, Meter_no) แบบ TRIM ทั้ง 2 ฝั่ง
      - ไม่มีเลข (แถว "รอ Gen เลข") -> เทียบ (SubArea_id, Meter_type_cd) และใช้ซ้ำเฉพาะตอน
        เจอตัวเดียวเท่านั้น เพราะถ้าเจอหลายตัวจะไม่รู้ว่าหมายถึงตัวไหน ปล่อยให้ INSERT ใหม่
    เทียบเฉพาะแถว UseOrNot = 1 -- มิเตอร์ที่ถูกปิดใช้งานไว้ไม่ควรถูกปลุกกลับมาโดยการ import
    """
    if meter_no:
        cursor.execute(
            """
            SELECT Meter_id, Meter_no, Meter_no_status
            FROM dbo.Contract_meter_ms
            WHERE LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
              AND Meter_type_cd = ?
              AND LTRIM(RTRIM(Meter_no)) = LTRIM(RTRIM(?))
              AND UseOrNot = 1
            ORDER BY Meter_id
            """,
            subarea_id, meter_type_cd, meter_no,
        )
        row = cursor.fetchone()
        return (row[0], row[1], row[2]) if row else None

    cursor.execute(
        """
        SELECT Meter_id, Meter_no, Meter_no_status
        FROM dbo.Contract_meter_ms
        WHERE LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
          AND Meter_type_cd = ?
          AND UseOrNot = 1
        ORDER BY Meter_id
        """,
        subarea_id, meter_type_cd,
    )
    found = cursor.fetchall()
    if len(found) == 1:
        r = found[0]
        return (r[0], r[1], r[2])
    return None


def commit_staged_rows(rows, user_id):
    logs = []
    stats = {'meter_ok': 0, 'meter_reused': 0, 'skipped': 0, 'errors': 0}
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
                # หา Meter_id เดิมก่อน -- ถ้าเจอจะส่งเข้า SP ให้เข้า branch UPDATE
                # (ใช้ cursor ตัวเดียวกับที่กำลัง commit อยู่ ให้เห็นแถวที่เพิ่ง insert ในรอบนี้ด้วย)
                existing = find_existing_meter(
                    cursor, r['subarea_id'], r['type_cd'], r['meter_no'],
                )
                reuse_id = existing[0] if existing else None

                # สำคัญ: branch UPDATE ของ SP สั่ง SET Meter_no = @Meter_no ตรงๆ และ auto-gen
                # เลขน้ำ (W001...) ทำงานแค่ใน branch INSERT เท่านั้น ถ้าแถวนี้ไม่มีเลขเครื่องวัด
                # (รอ Gen เลข) แล้วเราส่ง NULL เข้า UPDATE เลขที่ระบบ gen ไว้เดิมจะถูกล้างหาย
                # จึงต้องส่งเลข/สถานะเดิมของแถวนั้นกลับเข้าไปเพื่อรักษาค่าไว้
                if existing and not r['meter_no']:
                    meter_no_to_save, status_to_save = existing[1], existing[2]
                else:
                    meter_no_to_save, status_to_save = r['meter_no'], r['meter_no_status']

                meter_id = sp_meter_save(
                    cursor, r['location_id'], r['area_id'], r['subarea_id'], r['type_cd'],
                    meter_no_to_save, status_to_save, user_id, logs, r.get('phase_type'),
                    meter_id=reuse_id,
                )
                stats['meter_ok'] += 1
                if reuse_id:
                    stats['meter_reused'] += 1
                row_result['meter_id'] = meter_id
                row_result['reused'] = bool(reuse_id)
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
    except Exception:
        # error ที่หลุดออกมานอก try ของแต่ละแถว (เช่นตอน commit เอง) -- rollback ให้ชัดเจน
        # ไม่ปล่อยให้ไปพึ่งพฤติกรรม implicit rollback ตอน conn.close()
        conn.rollback()
        raise
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
                MAX(c.Contract_id) AS contract_id,
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
    """
    มิเตอร์ทั้งหมดที่ผูกกับสัญญาหนึ่ง -- ใช้ในหน้ายกเลิกสัญญา

    sp_Contract_Meter_SelectByContract คืนแต่ Location_id / Area_id ซึ่งเป็นรหัสล้วน
    (เช่น 'L01', 'A3') อ่านบนหน้าจอไม่รู้ว่าที่ไหน จึงเติมชื่อสถานที่/พื้นที่ให้ด้วย
    ยังเรียก SP เดิมเป็นตัวหา "มิเตอร์ของสัญญานี้" อยู่ (ไม่เขียน join ใหม่ซ้ำ)
    แล้วค่อย lookup ชื่อแยกอีก query เดียวจากรหัสที่ได้มา

    เหตุผลที่ lookup แยกไม่ join รวด: ผล SP เป็น result set ที่ join ต่อตรงๆ ใน SQL ไม่ได้
    (ต้องผ่าน temp table) ซึ่งซับซ้อนกว่าโดยไม่ได้อะไรเพิ่ม -- จำนวนพื้นที่ต่อสัญญามีไม่มาก
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
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if not rows:
            return rows

        # ชื่อสถานที่ (1 query ครอบคลุมทุกแถว) -- คีย์เป็น Location_id
        location_ids = {r.get('Location_id') for r in rows if r.get('Location_id')}
        location_names = {}
        if location_ids:
            ph = ','.join('?' for _ in location_ids)
            cursor.execute(
                f"SELECT Location_id, Location_name FROM dbo.Contract_location_ms "
                f"WHERE Location_id IN ({ph})",
                *location_ids,
            )
            location_names = {r[0]: r[1] for r in cursor.fetchall()}

        # ชื่อพื้นที่ -- คีย์เป็น (Location_id, Area_id) เพราะ Area_id ซ้ำได้ข้ามสถานที่
        area_pairs = {(r.get('Location_id'), r.get('Area_id'))
                      for r in rows if r.get('Location_id') and r.get('Area_id')}
        area_names = {}
        if area_pairs:
            conds = ' OR '.join('(Location_id = ? AND Area_id = ?)' for _ in area_pairs)
            params = [v for pair in area_pairs for v in pair]
            cursor.execute(
                f"SELECT Location_id, Area_id, Area_name FROM dbo.Contract_location_area_ms "
                f"WHERE {conds}",
                *params,
            )
            area_names = {(r[0], r[1]): r[2] for r in cursor.fetchall()}

        for r in rows:
            r['Location_name'] = location_names.get(r.get('Location_id'))
            r['Area_name'] = area_names.get((r.get('Location_id'), r.get('Area_id')))
            # ข้อมูลจริงมีชื่อที่ลงท้ายด้วยช่องว่าง/ขึ้นบรรทัดใหม่ติดมา (เช่น SubArea_name ของ A11
            # ลงท้ายด้วย '\n\n') ทำให้แสดงบนตารางเพี้ยน -- ตัดให้เรียบเหมือนที่ fetch_meters ทำ
            for key in ('Location_name', 'Area_name', 'SubArea_name'):
                if r.get(key):
                    r[key] = ' '.join(str(r[key]).split())
        return rows
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
            # ต้องมี ORDER BY เสมอ: ข้อมูลจริงมีพื้นที่ที่ลงทะเบียนมิเตอร์ประเภทเดียวกันซ้ำหลายตัว
            # (เช่น SubArea 'A10' มีมิเตอร์น้ำทั้ง 1014 และ 1038) ถ้าไม่สั่งเรียงลำดับ SQL Server
            # ไม่การันตีว่าจะคืนแถวไหนก่อน -> next() ด้านล่างอาจหยิบมิเตอร์คนละตัวในแต่ละครั้งที่
            # โหลดหน้า ทำให้เลขอ่านที่บันทึกไว้ใต้มิเตอร์ตัวหนึ่งดูเหมือนหายไปเอง
            # เรียงตาม Meter_id -> ได้ตัวที่ลงทะเบียนไว้ก่อน (เก่าสุด) อย่างคงที่ทุกครั้ง
            """
            SELECT Meter_id, Meter_type_cd, Meter_no, Meter_no_status, Phase_type
            FROM dbo.Contract_meter_ms
            WHERE SubArea_id = ? AND UseOrNot = 1
            ORDER BY Meter_type_cd, Meter_id
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
    จากตาราง dbo.Contract_meter_reading_tr พร้อม Contract_id/Contract_code ของสัญญาที่ผูกมิเตอร์นั้น

    คืนค่าเป็น dict {meter_id (int): {'Reading_before', 'Reading_after', 'Contract_id', 'Contract_code'}}

    ทำไมย้ายมาใช้ตารางนี้แทน Contract_Installment_tr_dt (เวอร์ชันเดิม):
      - ตารางนี้ผูกมิเตอร์ด้วย Meter_id (int) ตรงกับ Contract_meter_ms.Meter_id ได้เลย
        ต่างจาก Contract_Installment_tr_dt.Contract_meter_id ที่เป็น nvarchar เก็บข้อความอิสระ
        (เจอค่าจริงอย่าง 'aa2222', 'T061-6012811-YG') ซึ่งแมตช์กับทะเบียนมิเตอร์ไม่ได้เลย
      - เก็บรอบบิลเป็น Billing_year_be (พ.ศ. ตรงๆ) + Billing_month (1-12) ไม่ต้องแปลง ค.ศ.
        และไม่ต้องอ้าง YEAR()/MONTH() ของ Contract_effective_date
      - มี unique constraint (Meter_id, Billing_year_be, Billing_month) -> 1 มิเตอร์ต่อ 1 รอบบิล
        ได้แถวเดียวเท่านั้น ไม่กำกวมเหมือนตารางงวดที่เดือนเดียวมีได้หลายงวด/หลายเรต

    Contract_id/Contract_code เก็บอยู่ในตารางนี้โดยตรงแล้ว (ดู sql/Contract_meter_reading_tr_AddContract.sql)
    เป็น snapshot ว่าตอนบันทึกเลขอ่านรอบนั้น มิเตอร์ผูกอยู่กับสัญญาไหน แต่ยังมี OUTER APPLY
    เป็น fallback ผ่าน COALESCE เผื่อแถวเก่าที่บันทึกไว้ก่อนเพิ่มคอลัมน์ (ค่าเป็น NULL)
    ยังแสดงสัญญาได้ตามปกติ -- ใช้ TOP 1 กันมิเตอร์ที่ผูกหลายสัญญาทำให้ได้เลขอ่านซ้ำแถว
    """
    meter_ids = [int(m) for m in meter_ids if m]
    if not meter_ids:
        return {}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in meter_ids)
        cursor.execute(
            f"""
            SELECT r.Meter_id, r.Reading_before, r.Reading_after,
                   COALESCE(r.Contract_id, ct.Contract_id)     AS Contract_id,
                   COALESCE(r.Contract_code, ct.Contract_code) AS Contract_code
            FROM dbo.Contract_meter_reading_tr r
            OUTER APPLY (
                SELECT TOP 1 h.Contract_id, h.Contract_code
                FROM dbo.Contract_meter_tr t
                JOIN dbo.Contract_hrd_tr h ON h.Contract_id = t.Contract_id
                WHERE t.Meter_id = r.Meter_id AND t.UseOrNot = 1
                ORDER BY h.Contract_id DESC
            ) ct
            WHERE r.Billing_year_be = ?
              AND r.Billing_month = ?
              AND r.Meter_id IN ({placeholders})
            """,
            billing_year_be, billing_month, *meter_ids,
        )
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

        result = {}
        for r in rows:
            result[int(r['Meter_id'])] = {
                'Reading_before': r['Reading_before'],
                'Reading_after': r['Reading_after'],
                'Contract_id': r['Contract_id'],
                'Contract_code': r['Contract_code'],
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
                m.Meter_no, m.Meter_no_status, m.Phase_type, m.UseOrNot,
                m.Location_id, m.Area_id,
                l.Location_name, a.Area_name, s.SubArea_name,
                bc.bound_contracts
            FROM dbo.Contract_meter_ms m
            LEFT JOIN dbo.Contract_location_ms l
                   ON l.Location_id = m.Location_id
            LEFT JOIN dbo.Contract_location_area_ms a
                   ON a.Location_id = m.Location_id
                  AND a.Area_id = m.Area_id
            LEFT JOIN dbo.Contract_location_subarea_ms s
                   ON s.Location_id = m.Location_id
                  AND s.Area_id = m.Area_id
                  AND s.SubArea_id = m.SubArea_id
            OUTER APPLY (
                SELECT STRING_AGG(c.Contract_code, ', ') AS bound_contracts
                FROM dbo.Contract_meter_tr t
                JOIN dbo.Contract_hrd_tr c ON c.Contract_id = t.Contract_id
                WHERE t.Meter_id = m.Meter_id
            ) bc
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
            # ค้นได้จากชื่อสถานที่/พื้นที่/พื้นที่ย่อยด้วย เพราะหน้าจัดการมิเตอร์แสดงคอลัมน์
            # เหล่านี้แล้ว ถ้าค้นไม่ได้จะงงว่าเห็นอยู่บนจอแต่หาไม่เจอ
            sql += """ AND (
                m.SubArea_id LIKE ? OR
                m.Meter_no LIKE ? OR
                m.Location_id LIKE ? OR
                m.Area_id LIKE ? OR
                l.Location_name LIKE ? OR
                a.Area_name LIKE ? OR
                s.SubArea_name LIKE ? OR
                EXISTS (
                    SELECT 1 FROM dbo.Contract_meter_tr t2
                    JOIN dbo.Contract_hrd_tr c2 ON c2.Contract_id = t2.Contract_id
                    WHERE t2.Meter_id = m.Meter_id AND c2.Contract_code LIKE ?
                )
            )"""
            # ใช้ _to_sql_like_pattern เหมือน fetch_subareas -- escape % _ [ ที่ผู้ใช้พิมพ์มาจริง
            # ไม่งั้นค้นหา '%' จะกลายเป็น wildcard คืนทุกแถว แทนที่จะหาอักขระ % ตามที่พิมพ์
            like = _to_sql_like_pattern(search)
            params += [like] * 8
        # ไม่ใช้ GROUP BY แล้ว -- ย้าย STRING_AGG ไปอยู่ใน OUTER APPLY ข้างบนแทน
        # เหตุผล: SubArea_name เป็น nvarchar(MAX) ซึ่ง SQL Server ไม่ยอมให้ GROUP BY
        # และการใช้ OUTER APPLY ทำให้เพิ่มคอลัมน์ใหม่ได้โดยไม่ต้องไปต่อท้าย GROUP BY ทุกครั้ง
        sql += " ORDER BY m.Meter_id DESC"

        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for r in rows:
            r['bound_contracts'] = (r['bound_contracts'] or '').split(', ') if r['bound_contracts'] else []
            # ข้อมูลจริงมีชื่อที่ลงท้ายด้วยช่องว่าง/ขึ้นบรรทัดใหม่ติดมา (เช่น SubArea_name
            # ของ A11 ลงท้ายด้วย '\n\n') ทำให้แสดงบนตารางเพี้ยน -- ตัดให้เรียบก่อนส่งออก
            for key in ('Location_name', 'Area_name', 'SubArea_name'):
                if r.get(key):
                    r[key] = ' '.join(str(r[key]).split())
        return rows
    finally:
        conn.close()


def fetch_dashboard_stats():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # ต้องกรอง UseOrNot = 1 ให้ตรงกับตารางมิเตอร์ที่แสดงบนหน้า dashboard
        # (fetch_meters ใช้ status_filter='active' เป็นค่าเริ่มต้น) ไม่งั้นตัวเลขบนการ์ด
        # จะนับมิเตอร์ที่ปิดใช้งานรวมไปด้วย แล้วไม่ตรงกับจำนวนแถวที่ผู้ใช้เห็นในตาราง
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM Contract_location_subarea_ms) AS subarea_count,
                (SELECT COUNT(DISTINCT Contract_id) FROM Contract_meter_tr WHERE UseOrNot = 1) AS contract_count,
                (SELECT COUNT(*) FROM Contract_meter_ms WHERE Meter_type_cd = 9 AND UseOrNot = 1) AS water_count,
                (SELECT COUNT(*) FROM Contract_meter_ms WHERE Meter_type_cd = 8 AND UseOrNot = 1) AS electric_count,
                (SELECT COUNT(*) FROM Contract_meter_ms
                  WHERE Meter_no_status = N'รอ Gen เลข' AND UseOrNot = 1) AS pending_gen
        """)
        columns = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else {}
    finally:
        conn.close()


def save_meter_reading(meter_id, billing_year_be, billing_month, reading_before, reading_after, user_id,
                       contract_id=None, contract_code=None):
    """
    บันทึกเลขอ่านก่อน-หลังของมิเตอร์ 1 ตัว ในรอบบิลหนึ่ง ผ่าน sp_Contract_Meter_Reading_Save
    คืนค่า Reading_id ที่บันทึก (None ถ้า SP ไม่คืนค่ากลับมา)

    SP ทำ upsert ให้เอง: หาแถวของ (Meter_id + Billing_year_be + Billing_month)
    ถ้ายังไม่มีจะ INSERT ถ้ามีอยู่แล้วจะ UPDATE ทับ

    ปีส่งเป็น พ.ศ. ตรงๆ ไม่ต้องแปลง ค.ศ. เพราะคอลัมน์ Billing_year_be เก็บ พ.ศ. อยู่แล้ว

    contract_id/contract_code เก็บเป็น snapshot ว่าเลขอ่านรอบนี้อยู่ภายใต้สัญญาไหน
    SP ใช้ COALESCE ตอน UPDATE จึงไม่ล้างค่าเดิมเป็น NULL ถ้าผู้เรียกไม่ส่งสัญญามา

    ประวัติของฟังก์ชันนี้ (กันเข้าใจผิดซ้ำ):
      - เดิมเรียก SP ตัวนี้อยู่แล้ว แต่การเรียกหลุดหายไปตอน commit ที่แยก meters/services.py
        ออกเป็นแพ็กเกจ services/ แล้วถูกเขียนใหม่เป็น raw SQL ที่ยิงใส่ตารางผิดตัว
        (Contract_Installment_tr_dt ซึ่งจับคู่ Contract_meter_id ไม่ได้) ทำให้บันทึกไม่สำเร็จเลย
      - คอลัมน์ Contract_id/Contract_code เพิ่มเข้าตารางทีหลัง SP จึงต้องถูกแก้ให้รองรับด้วย
        (ดู sql/sp_Contract_Meter_Reading_Save_AddContract.sql)
    """
    if reading_before is not None and not isinstance(reading_before, int):
        raise ValueError(f"reading_before ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_before!r}")
    if reading_after is not None and not isinstance(reading_after, int):
        raise ValueError(f"reading_after ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_after!r}")

    contract_id = int(contract_id) if contract_id else None
    contract_code = (str(contract_code).strip() or None) if contract_code else None

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_Contract_Meter_Reading_Save
                @Meter_id        = ?,
                @Billing_year_be = ?,
                @Billing_month   = ?,
                @Reading_before  = ?,
                @Reading_after   = ?,
                @UserId          = ?,
                @Contract_id     = ?,
                @Contract_code   = ?
            """,
            int(meter_id), billing_year_be, billing_month,
            reading_before, reading_after, user_id, contract_id, contract_code,
        )
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
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