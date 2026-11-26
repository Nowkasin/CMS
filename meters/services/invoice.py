# meters/services/invoice.py
"""
ใบแจ้งหนี้ -- ค้นหาและดึงข้อมูลพิมพ์ใบแจ้งหนี้ (อ่านอย่างเดียว ไม่เขียนข้อมูล)

แทนฟอร์ม K2 FRM_4019_Invoice_CMS ตามแบบร่าง "ใบแจ้งหนี้ V1.3":
  หนึ่งใบแจ้งหนี้ = หนึ่งสัญญา + หนึ่งวันที่ตั้งหนี้ SAP (Contract_fi_date) รวมทุกเลขเอกสาร SAP
  ที่ตั้งหนี้วันเดียวกัน -- SAP ออกเลขเอกสารแยกต่อประเภท (ค่าเช่า / ค่าธรรมเนียมรายปี / ค่าประกัน ...)
  แต่ละบรรทัดในใบจึงแสดงเลขเอกสาร (Document) ของตัวเอง

แหล่งบรรทัด (_LINES_CTE):
  - Contract_Installment_tr ที่มีเลข SAP แล้ว ทุกประเภทรวมเงินประกัน (7) ตามแบบร่าง
    ประเภททั่วไปต้องมีแถวใน Contract_price_tr (เงื่อนไขเดียวกับ view v_contract_price_tr ที่ K2 ใช้)
    ยกเว้นค่าน้ำ/ค่าไฟ (8/9) ที่คิดตามมิเตอร์และไม่มีราคาตั้งไว้ในสัญญา
  - Contract_meter_reading_tr ที่มีเลข SAP แล้ว -- ค่าน้ำ/ค่าไฟรายมิเตอร์ พร้อมเลขมิเตอร์ก่อน/หลัง
    (หนึ่งบรรทัดต่อมิเตอร์ งวด = เดือนที่จดมิเตอร์)
ข้อความรายการของงวดใน Contract_Installment_tr ใช้ 'Doc Header Text' จาก sp_6000_Contact_Doc_invoice
(SP เดิมของ K2) เพื่อให้ข้อความพิเศษอย่างค่าใช้พื้นที่รายปีพร้อมช่วงวันที่ตรงกับ K2
"""
import datetime

from .db import get_db_connection
from .sql_utils import _to_sql_like_pattern

# ใบแจ้งหนี้ที่เลือกพิมพ์พร้อมกันได้สูงสุดต่อครั้ง -- กัน URL ยาวเกินและการเรียก SP จำนวนมาก
MAX_PRINT_DOCUMENTS = 100
# บรรทัดสูงสุดที่หน้าค้นหาดึงต่อครั้ง -- เกินนี้ให้ผู้ใช้ระบุคำค้นหรือเดือนให้แคบลง
MAX_SEARCH_ROWS = 2000
# Contract_type_price_ms: 8 ค่าน้ำประปา, 9 ค่าไฟฟ้า -- คิดตามมิเตอร์ อาจไม่มีแถวใน Contract_price_tr
UTILITY_TYPE_SQL = "('8', '9')"

# Contract_meter_ms.Meter_type_cd สลับกับรหัสค่าใช้จ่าย: มิเตอร์ 9 = น้ำ -> ค่าน้ำ '8', มิเตอร์ 8 = ไฟ -> ค่าไฟ '9'
_LINES_CTE = f"""
WITH lines AS (
    SELECT i.Contract_id, i.Contract_fi_doc, i.Contract_fi_date,
           CAST(i.Contract_type_price_id AS nvarchar(10)) AS Contract_type_price_id,
           tp.Contract_type_price_desc, d.Contract_debt_desc,
           CAST(i.Contract_debt_cd AS nvarchar(10)) AS Contract_debt_cd,
           CAST(i.Contract_Installment_month_year AS nvarchar(10)) AS Period,
           CASE WHEN LEFT(i.Contract_debt_cd, 1) = '1'
                THEN i.Contract_Installment_amt ELSE -i.Contract_Installment_amt END AS Amount,
           CAST(NULL AS varchar(50)) AS Meter_no,
           CAST(NULL AS int) AS Reading_before, CAST(NULL AS int) AS Reading_after,
           CAST(i.Contract_debt_to_SAP AS nvarchar(2)) AS Contract_debt_to_SAP,
           CAST(i.Contract_meeting_adj AS nvarchar(200)) AS Contract_meeting_adj,
           CAST(i.Contract_Installment_seq AS int) AS Line_seq, 'I' AS Line_source
    FROM dbo.Contract_Installment_tr i
    INNER JOIN dbo.Contract_type_price_ms tp ON tp.Contract_type_price_id = i.Contract_type_price_id
    INNER JOIN dbo.Contract_debt_ms d ON d.Contract_debt_cd = i.Contract_debt_cd
    WHERE i.Contract_fi_doc IS NOT NULL
      AND (i.Contract_type_price_id IN {UTILITY_TYPE_SQL}
           OR EXISTS (SELECT 1 FROM dbo.Contract_price_tr p
                      WHERE p.Contract_id = i.Contract_id
                        AND p.Contract_type_price_id = i.Contract_type_price_id))
    UNION ALL
    SELECT rd.Contract_id, rd.Contract_fi_doc, rd.Contract_fi_date,
           ut.Price_type, tp.Contract_type_price_desc, NULL, NULL,
           CONCAT(rd.Billing_year_be - 543, RIGHT('0' + CAST(rd.Billing_month AS varchar(2)), 2)),
           rd.Amount, ms.Meter_no, rd.Reading_before, rd.Reading_after,
           rd.Contract_debt_to_SAP, NULL, rd.Reading_id, 'M'
    FROM dbo.Contract_meter_reading_tr rd
    INNER JOIN dbo.Contract_meter_ms ms ON ms.Meter_id = rd.Meter_id
    CROSS APPLY (SELECT CASE ms.Meter_type_cd WHEN 9 THEN N'8' WHEN 8 THEN N'9' END AS Price_type) ut
    INNER JOIN dbo.Contract_type_price_ms tp ON tp.Contract_type_price_id = ut.Price_type
    WHERE rd.Contract_fi_doc IS NOT NULL
      AND rd.Contract_id IS NOT NULL
)
"""

# ลำดับบรรทัดตามแบบร่าง: ค่าใช้จ่ายตามสัญญา (ตามรหัสประเภท) ก่อน แล้วค่าไฟ ค่าน้ำ
_LINE_ORDER = """CASE l.Contract_type_price_id WHEN N'9' THEN 90 WHEN N'8' THEN 91
                      ELSE TRY_CONVERT(int, l.Contract_type_price_id) END,
                 l.Period, l.Meter_no, l.Line_seq"""


def fetch_invoice_years():
    """ปีที่สร้างสัญญา (พ.ศ.) ที่มีงวดตั้งหนี้แล้ว -- dropdown ในตัวกรองเพิ่มเติม"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT LTRIM(RTRIM(h.Contract_year))
            FROM dbo.Contract_hrd_tr h
            WHERE h.Contract_year IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM dbo.Contract_Installment_tr i
                  WHERE i.Contract_id = h.Contract_id AND i.Contract_fi_doc IS NOT NULL
              )
            ORDER BY 1 DESC
            """
        )
        return [row[0] for row in cursor.fetchall() if row[0]]
    finally:
        conn.close()


def fetch_invoice_locations():
    """สถานที่ตั้งตามสัญญา (Contract_tr.Contract_swu_location_name) สำหรับ dropdown"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT LTRIM(RTRIM(Contract_swu_location_name))
            FROM dbo.Contract_tr
            WHERE NULLIF(LTRIM(RTRIM(Contract_swu_location_name)), '') IS NOT NULL
            ORDER BY 1
            """
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_invoice_periods(limit=36):
    """
    เดือนที่ตั้งหนี้ (YYYYMM ค.ศ. ของ Contract_fi_date) ที่มีใบแจ้งหนี้ ล่าสุดก่อน
    ใช้ทำ dropdown เดือน และเป็นค่าเริ่มต้นของหน้า (เปิดมาเห็นเดือนล่าสุดทันที)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP {int(limit)} ym
            FROM (
                SELECT CONVERT(char(6), Contract_fi_date, 112) AS ym
                FROM dbo.Contract_Installment_tr
                WHERE Contract_fi_doc IS NOT NULL AND Contract_fi_date IS NOT NULL
                UNION
                SELECT CONVERT(char(6), Contract_fi_date, 112)
                FROM dbo.Contract_meter_reading_tr
                WHERE Contract_fi_doc IS NOT NULL AND Contract_fi_date IS NOT NULL
            ) x
            ORDER BY ym DESC
            """
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def _month_range(period):
    """'YYYYMM' -> (วันแรกของเดือน, วันแรกของเดือนถัดไป)"""
    year, month = int(period[:4]), int(period[4:])
    start = datetime.date(year, month, 1)
    end = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def search_invoices(query='', period='', contract_year='', start_from=None, end_to=None,
                    location=''):
    """
    บรรทัดใบแจ้งหนี้ที่ตั้งหนี้แล้ว (ผู้เรียกจัดกลุ่มเป็นใบ: สัญญา + วันที่ตั้งหนี้) ทุกตัวกรองไม่บังคับ

    query         -- ค้นช่องเดียว: รหัสสัญญา / ชื่อผู้เช่า / รหัสผู้เช่า SAP / เลขสัญญา / เลขเอกสาร SAP
                     (เลขเอกสารตรงบรรทัดใดก็ได้ ได้ทั้งใบนั้นกลับมา)
    period        -- เดือนที่ตั้งหนี้ YYYYMM (ค.ศ.)
    contract_year -- ปีที่สร้างสัญญา พ.ศ.
    start_from / end_to -- date: วันเริ่มสัญญาตั้งแต่ / วันสิ้นสุดสัญญาไม่เกิน

    จำกัด MAX_SEARCH_ROWS แถว -- ค้น "ทุกเดือน" โดยไม่มีคำค้นอาจได้ข้อมูลทั้งตาราง
    คืน (rows, truncated)
    """
    sql = _LINES_CTE + f"""
        SELECT TOP {MAX_SEARCH_ROWS + 1}
               l.*, h.Contract_code, h.Contract_year, h.UserOwner AS Contract_owner,
               t.Contract_swu_location_name, cu.SAPVendor_Id, cu.CompanyName
        FROM lines l
        INNER JOIN dbo.Contract_tr t ON t.Contract_id = l.Contract_id
        INNER JOIN dbo.Contract_hrd_tr h ON h.Contract_id = l.Contract_id
        OUTER APPLY (
            SELECT TOP 1 x.CompanyName, x.SAPVendor_Id
            FROM dbo.Contract_customer_tr x
            WHERE TRY_CONVERT(int, x.Contract_id) = l.Contract_id
        ) cu
        WHERE 1 = 1
    """
    params = []
    query = (query or '').strip()
    if query:
        like = _to_sql_like_pattern(query)
        sql += """ AND (LTRIM(RTRIM(h.Contract_code)) LIKE ?
                        OR cu.CompanyName LIKE ?
                        OR cu.SAPVendor_Id LIKE ?
                        OR CONVERT(nvarchar(20), l.Contract_id) = ?
                        OR EXISTS (SELECT 1 FROM lines x
                                   WHERE x.Contract_id = l.Contract_id
                                     AND (x.Contract_fi_date = l.Contract_fi_date
                                          OR (x.Contract_fi_date IS NULL AND l.Contract_fi_date IS NULL
                                              AND x.Contract_fi_doc = l.Contract_fi_doc))
                                     AND x.Contract_fi_doc LIKE ?))"""
        params += [like, like, like, query, like]
    if period:
        start, end = _month_range(period)
        sql += ' AND l.Contract_fi_date >= ? AND l.Contract_fi_date < ?'
        params += [start, end]
    if contract_year:
        sql += ' AND LTRIM(RTRIM(h.Contract_year)) = ?'
        params.append(str(contract_year).strip())
    if start_from:
        sql += ' AND t.Start_contract >= ?'
        params.append(start_from)
    if end_to:
        sql += ' AND t.End_contract <= ?'
        params.append(end_to)
    if location:
        sql += ' AND LTRIM(RTRIM(t.Contract_swu_location_name)) = ?'
        params.append(location)
    sql += f' ORDER BY l.Contract_fi_date DESC, h.Contract_code, l.Contract_id, {_LINE_ORDER}'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = _fetch_dicts(cursor, sql, params)
    finally:
        conn.close()
    truncated = len(rows) > MAX_SEARCH_ROWS
    return rows[:MAX_SEARCH_ROWS], truncated


def fetch_invoice_documents(keys):
    """
    ข้อมูลพิมพ์ใบแจ้งหนี้ทีละใบ

    keys -- [(contract_id, fi_date: date หรือ None, fi_doc หรือ None), ...] ตามลำดับที่ต้องการพิมพ์
            ใบปกติระบุด้วยวันที่ตั้งหนี้ ส่วนงวดเก่าที่ไม่มีวันที่ตั้งหนี้ระบุด้วยเลขเอกสาร
    คืน [{'contract_id', 'fi_date', 'docs': [เลขเอกสาร...], 'header', 'lines', 'total'}, ...]
    ใบที่ไม่พบบรรทัดหรือไม่พบสัญญาถูกข้าม
    """
    documents = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for contract_id, fi_date, fi_doc in keys:
            contract_id = str(contract_id)
            sql = _LINES_CTE + 'SELECT l.* FROM lines l WHERE CONVERT(nvarchar(20), l.Contract_id) = ?'
            params = [contract_id]
            if fi_date:
                sql += ' AND l.Contract_fi_date = ?'
                params.append(fi_date)
            else:
                sql += ' AND l.Contract_fi_date IS NULL AND l.Contract_fi_doc = ?'
                params.append(str(fi_doc))
            lines = _fetch_dicts(cursor, f'{sql} ORDER BY {_LINE_ORDER}', params)
            if not lines:
                continue
            header = _fetch_header(cursor, contract_id, fi_date)
            if header is None:
                continue
            docs = []
            for line in lines:
                if line['Contract_fi_doc'] not in docs:
                    docs.append(line['Contract_fi_doc'])
            texts = _fetch_doc_header_texts(cursor, contract_id, [
                doc for doc in docs
                if any(line['Line_source'] == 'I' and line['Contract_fi_doc'] == doc for line in lines)
            ])
            for line in lines:
                key = (line['Contract_fi_doc'], line['Line_seq'], (line.get('Contract_debt_cd') or '').strip())
                line['Doc Header Text'] = texts.get(key) if line['Line_source'] == 'I' else None
            documents.append({
                'contract_id': contract_id,
                'fi_date': fi_date,
                'docs': docs,
                'header': header,
                'lines': lines,
                'total': sum((line.get('Amount') or 0) for line in lines),
            })
    finally:
        conn.close()
    return documents


def _fetch_dicts(cursor, sql, params):
    cursor.execute(sql, params)
    if cursor.description is None:
        return []
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_doc_header_texts(cursor, contract_id, docs):
    """
    ข้อความรายการจาก sp_6000_Contact_Doc_invoice (SP เดิมของ K2) ต่อเลขเอกสาร
    คืน {(fi_doc, seq, debt_cd): 'Doc Header Text'} -- งวดที่ SP ไม่คืน (เช่น ไม่มีแถวราคา) ใช้ชื่อประเภทแทน
    """
    texts = {}
    for doc in docs:
        for row in _fetch_dicts(
            cursor,
            'EXEC dbo.sp_6000_Contact_Doc_invoice @p_Contract_id = ?, @p_Contract_fi_doc = ?',
            [contract_id, str(doc)],
        ):
            seq = row.get('Contract_Installment_seq')
            key = (str(doc), int(seq) if seq is not None else None, (row.get('Contract_debt_cd') or '').strip())
            texts[key] = (row.get('Doc Header Text') or '').strip() or None
    return texts


def _fetch_header(cursor, contract_id, fi_date):
    """หัวใบแจ้งหนี้: สถานที่/ที่อยู่ มศว จากสัญญา และชื่อ/ที่อยู่ผู้เช่าประกอบแบบเดียวกับ SP พิมพ์ของ K2"""
    rows = _fetch_dicts(
        cursor,
        """
        SELECT TOP 1 h.Contract_code, h.Contract_year, t.Contract_swu_address,
               t.Contract_swu_location_name, b.SAPVendor_Id, b.CompanyName,
               ISNULL(b.Vendor_RoomNo, '') + ISNULL(b.Vendor_Floor, '') + ISNULL(b.Vendor_Street2, '')
               + ISNULL(b.Street3, '') + ISNULL(b.Vendor_Street, '') + ISNULL(b.Vendor_HouseNumber, '')
               + ISNULL(b.Vendor_HouseNumberSupplement, '') + ISNULL(b.Vendor_Street4, '')
               + ISNULL(b.Street5, '') + ISNULL(b.DISTRICT_NAME, '') + ISNULL(b.AMPHUR_NAME, '')
               + ISNULL(b.PROVINCE_NAME, '') + ISNULL(b.Vendor_ZipCode, '') AS customer_address
        FROM dbo.Contract_tr t
        INNER JOIN dbo.Contract_hrd_tr h ON h.Contract_id = t.Contract_id
        LEFT JOIN dbo.v_contact_for_pdf b ON b.Contract_id = t.Contract_id
        WHERE CONVERT(nvarchar(20), t.Contract_id) = ?
        """,
        [contract_id],
    )
    if not rows:
        return None
    header = rows[0]
    header['Contract_fi_date'] = fi_date
    return header
