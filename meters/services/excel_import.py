# meters/services/excel_import.py
"""
ทุกอย่างที่เกี่ยวกับการอ่าน/แปลงไฟล์ Excel ตอน step1_upload (parse_excel_staged)
รวมถึง lookup ที่ใช้ตรวจสอบข้อมูลระหว่าง parse (find_subarea, find_contract_by_code)
"""
from openpyxl import load_workbook

from .db import get_db_connection
from .meters import find_existing_meter

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
    # --- เลขอ่านมิเตอร์ (ใช้ทั้งชีทน้ำและไฟ) ---
    # header จริงในไฟล์คือ 'เลขที่อ่านครั้งหลัง ตย. พ.ค.69' -- ข้อความ ตย. ท้ายหัวเปลี่ยนทุกเดือน
    # แต่ build_column_map เทียบแบบ "มีคำนี้อยู่ในหัว" จึงไม่กระทบ ห้ามใส่ ตย./เดือนในคีย์
    # หมายเหตุ: ในไฟล์คอลัมน์ "หลัง" อยู่ก่อนคอลัมน์ "ก่อน" -- map ตามชื่อ ไม่ใช้ตำแหน่ง
    'READING_AFTER': ['เลขที่อ่านครั้งหลัง'],
    'READING_BEFORE': ['เลขที่อ่านครั้งก่อน'],
    'READ_DATE': ['วันที่อ่านเลขมิเตอร์'],
    'AMOUNT': ['จำนวนเงินที่ต้องชำระ'],
}


def build_column_map(header_row):
    col_map = {}
    for field, keywords in COL_KEYS.items():
        for i, header in enumerate(header_row):
            if header and all(kw in str(header) for kw in keywords):
                col_map[field] = i
                break
    return col_map


def _cell(row, idx):
    """
    อ่านค่าจาก row ตาม index อย่างปลอดภัย -- โหมด read_only ของ openpyxl อาจคืนแถวที่สั้นกว่า
    header (ตัดเซลล์ว่างท้ายแถวทิ้ง) ถ้าเข้าถึง row[idx] ตรงๆ จะ IndexError
    """
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _parse_reading(raw):
    """
    แปลงเลขอ่านมิเตอร์จากเซลล์ Excel เป็นตัวเลข
    คืน (value, ok) -- ok=False แปลว่าเซลล์ไม่ว่างแต่แปลงเป็นตัวเลขไม่ได้ (ต้องเตือนผู้ใช้
    ไม่ใช่ข้ามเงียบๆ) ส่วนเซลล์ว่างจริงคืน (None, True)
    รองรับ int/float, ข้อความแบบ '1,234.50', และเลขที่เก็บเป็นข้อความ
    คืน int ถ้าเป็นจำนวนเต็ม เพื่อให้ JSON ใน session / การแสดงผลไม่เป็น 592.0
    """
    if raw is None or isinstance(raw, bool):
        return None, raw is None
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        s = str(raw).replace(',', '').replace('\u00a0', '').strip()
        if s in ('', '-'):
            return None, True
        try:
            val = float(s)
        except ValueError:
            return None, False
    return (int(val) if val.is_integer() else val), True


def _parse_read_date(raw):
    """
    วันที่อ่านมิเตอร์ -- ในไฟล์เป็นข้อความ '25/5/2569' แต่ถ้า Excel เก็บเป็นวันที่จริงจะได้
    datetime ซึ่ง JSON serialize ลง session ไม่ได้ จึงแปลงเป็นข้อความ d/m/พ.ศ. ให้เสมอ
    """
    if raw is None:
        return None
    if hasattr(raw, 'strftime'):
        year = raw.year + 543 if raw.year < 2400 else raw.year
        return f'{raw.day}/{raw.month}/{year}'
    s = str(raw).strip()
    return s or None


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


def find_registered_meter(subarea_id, meter_type_cd, meter_no):
    """
    เช็คตอน parse ว่ามิเตอร์แถวนี้ลงทะเบียนไว้ในระบบแล้วหรือยัง เพื่อบอกผู้ใช้ใน Step 2
    ว่าจะเป็นการอัปเดตตัวเดิม ไม่ใช่สร้างใหม่ (ใช้ logic จับคู่ชุดเดียวกับตอน commit จริง
    -- find_existing_meter ใน meters.py -- เพื่อให้ผลที่โชว์ตรงกับที่จะเกิดขึ้นจริง)
    คืนค่า Meter_id เดิม หรือ None
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        found = find_existing_meter(cursor, subarea_id, meter_type_cd, meter_no)
        return found[0] if found else None
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
    """
    อ่านไฟล์ Excel ที่อัปโหลดมาแล้วแปลงเป็นรายการแถว staged (ยังไม่เขียน DB)

    read_only=True ลดหน่วยความจำตอนอ่าน -- openpyxl โหมดปกติโหลดทุกเซลล์เป็น object
    ไว้ในหน่วยความจำทั้งไฟล์ ไฟล์ใหญ่จะกินแรมมาก ส่วนโหมดนี้อ่านแบบ stream
    เราใช้แค่ iter_rows(values_only=True) จึงไม่ต้องการความสามารถของโหมดปกติ
    ต้อง wb.close() เองในโหมดนี้ (ปล่อย handle ของไฟล์ชั่วคราว)

    โยน ValueError พร้อมข้อความไทยสำหรับผู้ใช้ 2 กรณี -- ชีทชื่อซ้ำเกิน 1
    และหาคอลัมน์ header ไม่เจอ ผู้เรียก (step1_upload) รับไปแสดงบนฟอร์ม
    """
    wb = load_workbook(uploaded_file, data_only=True, read_only=True)
    try:
        return _parse_workbook(wb)
    finally:
        wb.close()


def _parse_workbook(wb):
    water_sheet = find_contract_sheet(wb.sheetnames, 'น้ำ')
    elec_sheet = find_contract_sheet(wb.sheetnames, 'ไฟ')

    rows_out = []
    counter = {'idx': 0}
    # จำ key ที่เจอแล้วในไฟล์นี้ -> ใช้ตรวจแถวซ้ำกันเองภายในไฟล์ (ข้ามทั้ง 2 ชีทน้ำ/ไฟ)
    seen_in_file = {}

    def handle_sheet(sheet_name, type_cd):
        if not sheet_name:
            return
        type_label = 'น้ำ' if type_cd == 9 else 'ไฟฟ้า'

        ws = wb[sheet_name]
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        col = build_column_map(header_row)

        # เลขอ่านมิเตอร์ก่อน/หลังเป็นคอลัมน์บังคับ -- ถ้า header ไม่ตรง ให้แจ้งผู้ใช้ทันที
        # ดีกว่าปล่อยให้นำเข้าโดยไม่มีเลขอ่าน แบบที่เคยเงียบหายมาก่อน
        # (ถ้าต้องการให้ไฟล์เก่าที่ไม่มีคอลัมน์นี้ยังนำเข้าได้ ให้ย้าย 2 ตัวนี้ออกจาก required)
        required = [
            'SUBAREA', 'AREA', 'CONTRACT_NO', 'CONTRACT_CODE', 'CONFIRM', 'METER_NO',
            'READING_AFTER', 'READING_BEFORE',
        ]
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

            subarea_id = _cell(row, col['SUBAREA'])
            area_id = _cell(row, col['AREA'])
            loc_id = _cell(row, col['LOCATION']) if has_location else None
            if not subarea_id or not area_id:
                continue
            area_id, subarea_id = str(area_id).strip(), str(subarea_id).strip()
            loc_id = str(loc_id).strip() if loc_id else None

            contract_id = _cell(row, col['CONTRACT_NO'])
            contract_code = _cell(row, col['CONTRACT_CODE'])
            contract_code = str(contract_code).strip() if contract_code else contract_code
            confirm_flag = _cell(row, col['CONFIRM'])
            meter_no_raw = _cell(row, col['METER_NO'])

            # เลขอ่านมิเตอร์ -- อ่านทุกแถวตั้งแต่ต้น แถว error ก็ยังเห็นค่าจริงในตาราง review
            reading_after, after_ok = _parse_reading(_cell(row, col['READING_AFTER']))
            reading_before, before_ok = _parse_reading(_cell(row, col['READING_BEFORE']))

            counter['idx'] += 1
            entry = {
                'idx': counter['idx'],
                'type_cd': type_cd, 'type_label': type_label,
                'contract_year': _cell(row, col['YEAR']) if 'YEAR' in col else None,
                'customer_name': _cell(row, col['CUSTOMER_NAME']) if 'CUSTOMER_NAME' in col else None,
                'tax_id': _cell(row, col['TAX_ID']) if 'TAX_ID' in col else None,
                'location_id': loc_id, 'area_id': area_id,
                'subarea_id': subarea_id,
                'subarea_name': _cell(row, col['SUBAREA_NAME']) if 'SUBAREA_NAME' in col else None,
                'contract_id': contract_id, 'contract_code': contract_code,
                'meter_no': None, 'meter_no_status': None, 'phase_type': None,
                'reading_before': reading_before,
                'reading_after': reading_after,
                'read_date': _parse_read_date(_cell(row, col['READ_DATE'])) if 'READ_DATE' in col else None,
                'amount': _parse_reading(_cell(row, col['AMOUNT']))[0] if 'AMOUNT' in col else None,
                'status': 'ok', 'message': '',
            }

            if confirm_flag != 1 or meter_no_raw == 'ไม่มีมิเตอร์':
                entry['status'] = 'skip'
                entry['message'] = f'ไม่มีการคิดค่า{type_label}ในพื้นที่นี้'
                rows_out.append(entry)
                continue

            # กฎเลขอ่านต้องตรงกับหน้าแก้ไขมิเตอร์ (edit_meter ใน views/dashboard.py) เพราะ commit
            # เรียก save_meter_reading ตัวเดียวกัน: จำนวนเต็ม >= 0 และเลขหลังต้องไม่น้อยกว่าเลขก่อน
            # -- ผิดกฎ = error (บล็อกที่ Step 2) ส่วนขาดไปข้างเดียว/ทั้งคู่ = แค่เตือน
            reading_error = ''
            reading_warning = ''
            if not after_ok or not before_ok:
                reading_error = 'เลขอ่านมิเตอร์ก่อน/หลังไม่ใช่ตัวเลข -- ตรวจสอบเซลล์ในไฟล์'
            elif any(v is not None and (not isinstance(v, int) or v < 0)
                     for v in (reading_before, reading_after)):
                reading_error = 'เลขอ่านมิเตอร์ต้องเป็นจำนวนเต็มและไม่ติดลบ -- ตรวจสอบเซลล์ในไฟล์'
            elif (reading_before is not None and reading_after is not None
                  and reading_after < reading_before):
                reading_error = (
                    f'เลขหลัง ({reading_after:,}) น้อยกว่าเลขก่อน ({reading_before:,}) '
                    f'-- มิเตอร์เดินไปข้างหน้าเท่านั้น ตรวจสอบว่าพิมพ์สลับหรือผิด '
                    f'(ถ้าเปลี่ยนเครื่อง/หมุนครบรอบให้แจ้งผู้ดูแลระบบ)'
                )
            elif reading_before is None and reading_after is None:
                reading_warning = 'ไม่มีเลขอ่านมิเตอร์ก่อนและหลังในแถวนี้ -- จะไม่บันทึกเลขอ่านรอบนี้'
            elif reading_before is None or reading_after is None:
                reading_warning = 'มีเลขอ่านมิเตอร์เพียงข้างเดียว (ก่อนหรือหลัง) ในแถวนี้'
            entry['reading_warning'] = reading_warning

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
            if type_cd == 8 and 'PHASE' in col and _cell(row, col['PHASE']):
                entry['phase_type'] = '3เฟส' if '3' in str(_cell(row, col['PHASE'])) else '1เฟส'

            if reading_error:
                entry['status'] = 'error'
                entry['message'] = reading_error
                rows_out.append(entry)
                continue

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

            # --- เช็คซ้ำ 2 แบบ ให้ผู้ใช้เห็นก่อนกดยืนยันใน Step 3 ---
            dup_key = (subarea_id, type_cd, entry['meter_no'])

            # 1) ซ้ำกันเองในไฟล์ที่อัปโหลดมา -> ข้ามแถวหลัง (แถวแรกครอบคลุมอยู่แล้ว)
            if dup_key in seen_in_file:
                entry['status'] = 'skip'
                entry['message'] = (
                    f"ซ้ำกับแถวที่ {seen_in_file[dup_key]} ในไฟล์นี้ (พื้นที่/ประเภท/เลขเครื่องวัดเดียวกัน) -- ข้ามแถวนี้"
                )
                rows_out.append(entry)
                continue
            seen_in_file[dup_key] = entry['idx']

            # 2) มีอยู่ในทะเบียนมิเตอร์แล้ว -> ยังนำเข้าต่อได้ แต่จะเป็นการอัปเดตตัวเดิม
            #    (commit_staged_rows จะส่ง Meter_id เดิมเข้า SP ให้เข้า branch UPDATE)
            existing_meter_id = find_registered_meter(subarea_id, type_cd, entry['meter_no'])
            if existing_meter_id:
                entry['status'] = 'duplicate'
                entry['existing_meter_id'] = existing_meter_id
                entry['message'] = f"มีมิเตอร์นี้ในระบบแล้ว (Meter_id #{existing_meter_id}) จะอัปเดตตัวเดิม ไม่สร้างใหม่"

            # แนบคำเตือนเลขอ่านท้าย message (แถว ok / duplicate เท่านั้น)
            if reading_warning:
                entry['message'] = f"{entry['message']} | {reading_warning}" if entry['message'] else reading_warning

            rows_out.append(entry)

    handle_sheet(water_sheet, 9)
    handle_sheet(elec_sheet, 8)

    summary = {
        'total': len(rows_out),
        'ok': sum(1 for r in rows_out if r['status'] == 'ok'),
        'duplicate': sum(1 for r in rows_out if r['status'] == 'duplicate'),
        'skip': sum(1 for r in rows_out if r['status'] == 'skip'),
        'error': sum(1 for r in rows_out if r['status'] == 'error'),
    }

    return {
        'rows': rows_out,
        'summary': summary,
        'water_sheet_found': bool(water_sheet),
        'elec_sheet_found': bool(elec_sheet),
    }