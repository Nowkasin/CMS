"""
ทะเบียนมิเตอร์ / พื้นที่ย่อย / เลขอ่านรายรอบ -- query ของหน้าแดชบอร์ด หน้าจัดการมิเตอร์
และหน้าแก้ไขมิเตอร์ (การนำเข้าจาก Excel แยกไปอยู่ที่ meter_import.py)
"""
from .db import get_db_connection
from .meter_import import sp_meter_reading_save, sp_meter_save
from .sql_utils import _to_sql_like_pattern


def fetch_subareas(search=None, type_filter=None):
    """
    1 แถว = 1 พื้นที่ย่อยที่มีมิเตอร์ลงทะเบียนอยู่ -- เป็นชุดข้อมูลที่ตารางหน้า dashboard ใช้แสดง

    type_filter: '9' = เฉพาะพื้นที่ที่มีมิเตอร์น้ำ, '8' = เฉพาะที่มีมิเตอร์ไฟฟ้า, อื่นๆ = ไม่กรอง
      กรองด้วย "จำนวนมิเตอร์ของประเภทนั้น > 0" ไม่ใช่ "มีเลขมิเตอร์" เพราะมิเตอร์ที่ยัง
      รอ Gen เลขจะมี Meter_no เป็น NULL แต่ก็ถือว่าพื้นที่นั้นมีมิเตอร์ประเภทนั้นแล้ว

    search: ค้นได้จากเลขที่สัญญา / รหัสลูกหนี้ / ชื่อลูกหนี้ / เลขมิเตอร์ / รหัส+ชื่อพื้นที่ย่อย
      ให้ตรงกับที่ช่องค้นหาบนหน้าจอโฆษณาไว้ (เดิมกรองแต่ Contract_code อย่างเดียว
      ค้นชื่อลูกหนี้หรือเลขมิเตอร์แล้วได้ 0 แถวทุกครั้ง)
      ใช้ MAX(CASE WHEN ... THEN 1 ELSE 0 END) = 1 เพราะต้องการความหมายว่า
      "มีมิเตอร์ตัวใดตัวหนึ่งในกลุ่มนี้ที่ตรงคำค้น" -- MAX(m.Meter_no) LIKE ? จะเทียบแค่
      เลขมิเตอร์ตัวที่มากที่สุดในกลุ่ม ตัวอื่นในพื้นที่เดียวกันจะค้นไม่เจอ
    """
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
                COUNT(CASE WHEN m.Meter_type_cd = 9 THEN 1 END) AS water_meter_count,
                COUNT(CASE WHEN m.Meter_type_cd = 8 THEN 1 END) AS electric_meter_count,
                MAX(c.Contract_id) AS contract_id,
                MAX(c.Contract_code) AS contract_code,
                MAX(cu.Customer_id) AS customer_id,
                MAX(cu.CompanyName) AS customer_name
            FROM Contract_meter_ms m
            LEFT JOIN Contract_location_subarea_ms s ON s.SubArea_id = m.SubArea_id
            LEFT JOIN Contract_meter_tr t ON t.Meter_id = m.Meter_id AND t.UseOrNot = 1
            LEFT JOIN Contract_hrd_tr c ON c.Contract_id = t.Contract_id
            -- Contract_customer_tr.Contract_id เป็น nvarchar(50) แต่ Contract_hrd_tr.Contract_id
            -- เป็น int -- ถ้า join ตรงๆ SQL Server จะ implicit convert ฝั่ง nvarchar เป็น int
            -- แล้วพังทั้ง query ทันทีที่มีแถวไหนเก็บค่าที่แปลงไม่ได้ (ว่าง/มีตัวอักษร/มี CR LF ติดมา)
            -- TRY_CONVERT ทำให้แถวนั้นกลายเป็น NULL (คือหาลูกหนี้ไม่เจอ) แทนที่จะทำให้หน้าจอล่ม
            LEFT JOIN Contract_customer_tr cu
                   ON TRY_CONVERT(int, REPLACE(REPLACE(cu.Contract_id, CHAR(13), ''), CHAR(10), ''))
                      = c.Contract_id
            -- ต้องกรอง UseOrNot = 1 ให้ตรงกับที่อื่นบนหน้าเดียวกัน: การ์ดสถิติ
            -- (fetch_dashboard_stats) และหน้าแก้ไขมิเตอร์ (fetch_subarea_meters) กรอง
            -- UseOrNot = 1 ทั้งคู่ เดิมฟังก์ชันนี้ไม่กรองเลย จึงนับมิเตอร์ที่ปิดใช้งานรวมด้วย
            -- (52 ตัว vs 50 ตัว) และ MAX(Meter_no) อาจหยิบเลขของมิเตอร์ที่เลิกใช้แล้วมาโชว์
            -- ทำให้ตารางแสดงเลขมิเตอร์ที่หน้าแก้ไขบอกว่า "ยังไม่มีมิเตอร์"
            WHERE m.UseOrNot = 1
            GROUP BY m.Location_id, m.Area_id, m.SubArea_id, s.SubArea_name
        """
        params = []
        having = []
        if search:
            # ห้ามใส่ ESCAPE '[' -- _to_sql_like_pattern หนีอักขระพิเศษด้วย character class
            # แบบ [%] [_] [[] อยู่แล้ว ถ้าตั้ง '[' เป็น escape char ด้วย '[%' จะกลายเป็น % ตัวจริง
            # แล้วตามด้วย ']' ที่ต้องมีในข้อมูลจริง ค้นหา '50%' จึงไปหา '50%]' แทน
            having.append("""MAX(CASE WHEN
                    c.Contract_code LIKE ? OR
                    cu.Customer_id  LIKE ? OR
                    cu.CompanyName  LIKE ? OR
                    m.Meter_no      LIKE ? OR
                    m.SubArea_id    LIKE ? OR
                    s.SubArea_name  LIKE ?
                THEN 1 ELSE 0 END) = 1""")
            params += [_to_sql_like_pattern(search)] * 6
        if type_filter == '9':
            having.append("COUNT(CASE WHEN m.Meter_type_cd = 9 THEN 1 END) > 0")
        elif type_filter == '8':
            having.append("COUNT(CASE WHEN m.Meter_type_cd = 8 THEN 1 END) > 0")
        if having:
            sql += " HAVING " + " AND ".join(having)
        sql += " ORDER BY m.Location_id, m.Area_id, m.SubArea_id"

        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        # ข้อมูลจริงมีชื่อที่ลงท้ายด้วยช่องว่าง/ขึ้นบรรทัดใหม่ติดมา (SubArea_name ของ A11
        # ลงท้ายด้วย '\n\n') ทำให้แถวในตารางสูงไม่เท่ากัน -- ตัดให้เรียบเหมือนที่ fetch_meters ทำ
        for r in rows:
            if r.get('SubArea_name'):
                r['SubArea_name'] = ' '.join(str(r['SubArea_name']).split())
        return rows
    finally:
        conn.close()


def fetch_subarea_options(include_subarea_id=None):
    """
    พื้นที่ย่อย "ทั้งหมด" ใน master สำหรับ dropdown เลือกพื้นที่ในฟอร์มเพิ่ม/แก้ไขมิเตอร์

    ต้องเป็นฟังก์ชันแยกจาก fetch_subareas() -- fetch_subareas() ขึ้นต้นด้วย
    FROM Contract_meter_ms จึงคืนเฉพาะพื้นที่ "ที่มีมิเตอร์อยู่แล้ว" (13 จาก 469 แห่ง)
    ใช้เป็น dropdown ของหน้าเพิ่มมิเตอร์ไม่ได้ เพราะทำให้เพิ่มมิเตอร์ให้พื้นที่ใหม่ไม่ได้เลย
    (ต้องมีมิเตอร์อยู่แล้วจึงจะเลือกพื้นที่นั้นได้ = ไก่กับไข่)

    คืนค่าเป็นรายการกลุ่มพร้อมใช้ทำ <optgroup>:
        [{'label': '<สถานที่> › <พื้นที่>', 'items': [{...}, ...]}, ...]
    เพราะ 469 ตัวเลือกใน select เดียวแบนๆ หาไม่เจอ -- จัดกลุ่มตามสถานที่/พื้นที่ให้ไล่ดูได้

    include_subarea_id: พื้นที่ที่ถูกเลือกอยู่ตอนนี้ -- ต้องอยู่ในรายการเสมอแม้จะถูกปิดใช้งาน
    ใน master (UseOrNot = '0') ไม่งั้นเปิดหน้าแก้ไขมิเตอร์ของพื้นที่นั้นแล้ว dropdown จะ
    ไม่มีค่าเดิมให้เลือก กดบันทึกจะกลายเป็น "กรุณาเลือกพื้นที่ย่อย" ทั้งที่ผู้ใช้ไม่ได้แก้อะไร
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # UseOrNot ของตารางนี้เป็น nvarchar(1) ('1'/'0'/NULL) ไม่ใช่ bit -- เทียบเป็นสตริง
        # แถวที่เป็น NULL (มี 3 แถว) ไม่ฟันธงว่าปิดใช้งาน จึงยังแสดงไว้ ดีกว่าซ่อนไปเงียบๆ
        cursor.execute(
            """
            SELECT s.Location_id, s.Area_id, s.SubArea_id, s.SubArea_name, s.UseOrNot,
                   l.Location_name, a.Area_name, mc.meter_count
            FROM dbo.Contract_location_subarea_ms s
            LEFT JOIN dbo.Contract_location_ms l
                   ON l.Location_id = s.Location_id
            LEFT JOIN dbo.Contract_location_area_ms a
                   ON a.Location_id = s.Location_id AND a.Area_id = s.Area_id
            OUTER APPLY (
                SELECT COUNT(*) AS meter_count
                FROM dbo.Contract_meter_ms m
                WHERE m.SubArea_id = s.SubArea_id AND m.UseOrNot = 1
            ) mc
            WHERE s.UseOrNot IS NULL OR s.UseOrNot <> '0' OR s.SubArea_id = ?
            ORDER BY l.Location_name, a.Area_name, s.SubArea_id
            """,
            include_subarea_id,
        )
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

        groups = []
        for r in rows:
            # ข้อมูลจริงมีช่องว่าง/ขึ้นบรรทัดใหม่ติดท้ายชื่อ (เช่น Area_name ของ A ลงท้ายด้วย
            # ช่องว่าง, SubArea_name ของ A11 ลงท้ายด้วย '\n\n') -- ตัดให้เรียบก่อนเอาไปทำ label
            for key in ('Location_name', 'Area_name', 'SubArea_name'):
                if r.get(key):
                    r[key] = ' '.join(str(r[key]).split())
            r['is_inactive'] = (r.get('UseOrNot') == '0')
            # 12 พื้นที่ย่อยหาแถวใน Contract_location_area_ms ไม่เจอ -> ไม่มีชื่อพื้นที่
            # ใช้รหัสพื้นที่แทนไปก่อน ดีกว่าขึ้น label ว่าง แล้วไม่รู้ว่ากลุ่มนี้คือที่ไหน
            area_label = r.get('Area_name') or r.get('Area_id') or '-'
            label = f"{r.get('Location_name') or r.get('Location_id') or '-'} › {area_label}"
            if not groups or groups[-1]['label'] != label:
                groups.append({'label': label, 'items': []})
            groups[-1]['items'].append(r)
        return groups
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
            -- Area_id ซ้ำได้ข้ามสถานที่ ต้อง join ด้วย Location_id คู่กันเสมอ (เหมือน fetch_meters)
            LEFT JOIN dbo.Contract_location_area_ms a
                   ON a.Location_id = s.Location_id AND a.Area_id = s.Area_id
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
            -- Contract_customer_tr.Contract_id เป็น nvarchar -- join กับ int ตรงๆ จะ implicit
            -- convert แล้วพังทั้ง query เมื่อเจอแถวที่แปลงไม่ได้ ใช้ TRY_CONVERT แบบเดียวกับ fetch_subareas
            OUTER APPLY (
                SELECT TOP 1 x.Customer_id, x.CompanyName
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, REPLACE(REPLACE(x.Contract_id, CHAR(13), ''), CHAR(10), ''))
                      = c.Contract_id
            ) cu
            WHERE t.SubArea_id = ? AND t.UseOrNot = 1
            -- พื้นที่ที่ผูกหลายสัญญา: เลือกสัญญาล่าสุดอย่างคงที่ (ตรงกับ fetch_readings_for_meters)
            -- ไม่งั้น SQL Server คืนแถวไหนก่อนก็ได้ และค่านี้ถูกบันทึกลงแถวเลขอ่านด้วย
            ORDER BY c.Contract_id DESC
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
        # เลิกนับ subarea_count (COUNT(*) ทั้งตาราง Contract_location_subarea_ms = 469 แถว)
        # ออกไปแล้ว -- ไม่มีที่ไหนบนหน้าจอใช้ค่านั้น และมันสื่อผิดด้วย เพราะพื้นที่ย่อยที่มี
        # มิเตอร์จริงมีแค่ 13 แห่ง ตัวเลข 469 คือพื้นที่ทั้งหมดใน master ซึ่งไม่เกี่ยวกับหน้านี้
        cursor.execute("""
            SELECT
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
    ฟังก์ชันนี้เปิด connection ของตัวเองและ commit ทันที (ใช้จากหน้าแก้ไขมิเตอร์) -- ส่วนที่ต้อง
    อยู่ใน transaction เดียวกับงานอื่น (เช่น commit_staged_rows) ให้เรียก sp_meter_reading_save()
    ด้วย cursor ของ transaction นั้นแทน

    ประวัติของฟังก์ชันนี้ (กันเข้าใจผิดซ้ำ):
      - เดิมเรียก SP ตัวนี้อยู่แล้ว แต่การเรียกหลุดหายไปตอน commit ที่แยก meters/services.py
        ออกเป็นแพ็กเกจ services/ แล้วถูกเขียนใหม่เป็น raw SQL ที่ยิงใส่ตารางผิดตัว
        (Contract_Installment_tr_dt ซึ่งจับคู่ Contract_meter_id ไม่ได้) ทำให้บันทึกไม่สำเร็จเลย
      - คอลัมน์ Contract_id/Contract_code เพิ่มเข้าตารางทีหลัง SP จึงต้องถูกแก้ให้รองรับด้วย
        (ดู sql/sp_Contract_Meter_Reading_Save_AddContract.sql)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        reading_id = sp_meter_reading_save(
            cursor, meter_id, billing_year_be, billing_month, reading_before, reading_after,
            user_id, contract_id=contract_id, contract_code=contract_code,
        )
        conn.commit()
        return reading_id
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


# ความยาวสูงสุดของคอลัมน์ใน Contract_meter_ms -- ตรวจฝั่งแอปก่อนส่งเข้า DB
# ถ้าไม่ตรวจ SQL Server จะโยน "String or binary data would be truncated" ซึ่ง view
# แปลงเป็นข้อความ generic ("บันทึกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล")
# ผู้ใช้จึงไม่รู้ว่าพิมพ์ยาวเกินช่องไหน (แพตเทิร์นเดียวกับ MAX_PHASE_TYPE_LEN ใน phase.py)
MAX_METER_NO_LEN = 50       # Meter_no     varchar(50)
MAX_METER_REMARK_LEN = 200  # Meter_remark nvarchar(200)
MAX_PHASE_TYPE_LEN_METER = 10   # Phase_type   varchar(10)


def save_standalone_meter(subarea_id, meter_type_cd, meter_no, phase_type, user_id, meter_id=None,meter_remark=None, use_or_not=1):
    for value, limit, label in (
        (meter_no, MAX_METER_NO_LEN, 'เลขประจำเครื่องวัด'),
        (meter_remark, MAX_METER_REMARK_LEN, 'หมายเหตุ'),
        (phase_type, MAX_PHASE_TYPE_LEN_METER, 'ระบบไฟฟ้า'),
    ):
        if value and len(str(value)) > limit:
            raise ValueError(
                f'{label}ยาวเกินกำหนด -- ใส่ได้ไม่เกิน {limit} อักขระ '
                f'(ที่กรอกมา {len(str(value))} อักขระ)'
            )

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