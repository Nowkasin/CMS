# meters/services/excel_import.py
"""
ทุกอย่างที่เกี่ยวกับการอ่าน/แปลงไฟล์ Excel ตอน step1_upload (parse_excel_staged)
รวมถึง lookup ที่ใช้ตรวจสอบข้อมูลระหว่าง parse (find_subarea, find_contract_by_code)
"""
from openpyxl import load_workbook

from .db import get_db_connection

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

    ใช้ LTRIM(RTRIM(...)) ทุกฝั่งเทียบ เพราะเจอมาแล้วว่า Contract_hrd_tr.Contract_code
    บางแถวมีอักขระแฝงต่อท้าย (ดู find_contract_by_code) เผื่อ Location_id/Area_id/
    SubArea_id มีปัญหาเดียวกันได้เหมือนกัน กันไว้ก่อนทั้งหมด
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if location_id:
            cursor.execute(
                """
                SELECT Location_id, Area_id, SubArea_id, SubArea_name
                FROM dbo.Contract_location_subarea_ms
                WHERE LTRIM(RTRIM(Location_id)) = LTRIM(RTRIM(?))
                  AND LTRIM(RTRIM(Area_id)) = LTRIM(RTRIM(?))
                  AND LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
                """,
                location_id, area_id, subarea_id,
            )
        else:
            cursor.execute(
                """
                SELECT Location_id, Area_id, SubArea_id, SubArea_name
                FROM dbo.Contract_location_subarea_ms
                WHERE LTRIM(RTRIM(Area_id)) = LTRIM(RTRIM(?))
                  AND LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
                """,
                area_id, subarea_id,
            )
        return cursor.fetchone()
    finally:
        conn.close()


def find_contract_by_code(contract_code):
    """
    เช็คว่ารหัสสัญญานี้มีอยู่จริงใน Contract_hrd_tr หรือไม่

    ใช้ TRIM ทั้ง 2 ฝั่งก่อนเทียบ เพราะเจอแล้วว่าบางแถวใน Contract_hrd_tr
    มีอักขระที่มองไม่เห็น (ช่องว่างเกิน/ขึ้นบรรทัดใหม่) ติดอยู่ท้ายค่า Contract_code
    (เช่น 'AI5-AI6/2569' จริงๆ เก็บเป็น 'AI5-AI6/2569 ' ในฐานข้อมูล) ทำให้เทียบแบบ
    exact match ตรงๆ ไม่เจอ ทั้งที่ข้อมูลมีอยู่จริง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Contract_id, Contract_code FROM dbo.Contract_hrd_tr "
            "WHERE LTRIM(RTRIM(Contract_code)) = LTRIM(RTRIM(?))",
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
            area_id, subarea_id = str(area_id).strip(), str(subarea_id).strip()
            loc_id = str(loc_id).strip() if loc_id else None

            contract_id = row[col['CONTRACT_NO']]
            contract_code = row[col['CONTRACT_CODE']]
            contract_code = str(contract_code).strip() if contract_code else contract_code
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

            contract_match = find_contract_by_code(contract_code)
            if not contract_match:
                entry['status'] = 'error'
                entry['message'] = f"ไม่พบรหัสสัญญา '{contract_code}' ในระบบ"
                rows_out.append(entry)
                continue

            # ใช้ Contract_id จริงจาก DB (ตัวเลข ไม่มีปัญหาเรื่องช่องว่าง/อักขระแฝงแบบข้อความ)
            # แทน contract_code ตอนผูกกับสัญญาจริงใน commit_staged_rows -- กันปัญหาเดิม
            # ซ้ำอีกรอบตอน SP เทียบ Contract_code แบบ exact match ภายใน
            entry['db_contract_id'] = contract_match[0]

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