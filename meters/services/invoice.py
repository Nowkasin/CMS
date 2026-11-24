# meters/services/invoice.py
"""
ใบแจ้งหนี้ -- ค้นหางวดที่ตั้งหนี้แล้ว และดึงข้อมูลพิมพ์ใบแจ้งหนี้ (อ่านอย่างเดียว ไม่เขียนข้อมูล)

แทนฟอร์ม K2 FRM_4019_Invoice_CMS:
  - รายการค้นหา: งวดใน Contract_Installment_tr ที่มีเลขตั้งหนี้ SAP แล้ว (Contract_fi_doc)
    ผ่าน view เดิม v_contract_price_tr -- เงื่อนไขเดียวกับ sp_6000_Contract_select_invoice
    (fi_doc ไม่ว่าง และไม่ใช่ประเภทค่าธรรมเนียม 7)
  - ข้อมูลพิมพ์: เรียก sp_6000_Contact_Doc_invoice เดิมที่ K2 ใช้สร้าง PDF จึงได้ตัวเลข
    ข้อความรายการ ที่อยู่ และปีงบประมาณตรงกับใบแจ้งหนี้ของ K2
หนึ่งใบแจ้งหนี้ = หนึ่งคู่ (Contract_id, Contract_fi_doc) อาจมีหลายบรรทัด
"""
from collections import OrderedDict

from .db import get_db_connection
from .sql_utils import _to_sql_like_pattern

# ใบแจ้งหนี้ที่เลือกพิมพ์พร้อมกันได้สูงสุดต่อครั้ง -- กัน URL ยาวเกินและการเรียก SP ทีละใบจำนวนมาก
MAX_PRINT_DOCUMENTS = 100


def fetch_invoice_years():
    """ปีที่สร้างสัญญา (พ.ศ.) ที่มีงวดตั้งหนี้แล้ว -- ใช้ทำ dropdown ช่องบังคับของหน้าค้นหา"""
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


def search_invoices(contract_year, period='', contract_code='', start_from=None, end_to=None,
                    location='', name=''):
    """
    งวดที่ตั้งหนี้แล้วตามตัวกรอง (ตัวกรองเดียวกับฟอร์ม K2) เรียงตามรหัสสัญญาและงวด

    contract_year -- ปีที่สร้างสัญญา พ.ศ. (บังคับ ผู้เรียกต้องตรวจก่อน)
    period        -- ประจำงวด YYYYMM (ค.ศ.) ตามที่เก็บใน Contract_Installment_month_year
    start_from / end_to -- date: วันเริ่มสัญญาตั้งแต่ / วันสิ้นสุดสัญญาไม่เกิน
    """
    sql = """
        SELECT a.Contract_id, a.Contract_code, a.Contract_year, a.Contract_Installment_seq,
               a.Contract_debt_desc, a.Contract_Installment_month_year, a.Contract_type_price_desc,
               a.Contract_duedate, a.Installment_amt_by_debt AS Amount,
               a.Contract_debt_to_SAP, i.Contract_meeting_adj, a.Contract_fi_doc, a.Contract_fi_date,
               a.UserEntry AS Contract_owner, a.Contract_swu_location_name,
               cu.CompanyName
        FROM dbo.v_contract_price_tr a
        INNER JOIN dbo.Contract_Installment_tr i
                ON i.Contract_id = a.Contract_id
               AND i.Contract_Installment_seq = a.Contract_Installment_seq
               AND i.Contract_debt_cd = a.Contract_debt_cd
               AND i.Contract_type_price_id = a.Contract_type_price_id
        OUTER APPLY (
            SELECT TOP 1 x.CompanyName
            FROM dbo.Contract_customer_tr x
            WHERE TRY_CONVERT(int, x.Contract_id) = a.Contract_id
        ) cu
        WHERE a.Contract_fi_doc IS NOT NULL
          AND a.Contract_type_price_id <> '7'
          AND LTRIM(RTRIM(a.Contract_year)) = ?
    """
    params = [str(contract_year).strip()]
    if period:
        sql += ' AND a.Contract_Installment_month_year = ?'
        params.append(period)
    if contract_code:
        sql += ' AND LTRIM(RTRIM(a.Contract_code)) LIKE ?'
        params.append(_to_sql_like_pattern(contract_code))
    if start_from:
        sql += ' AND a.Start_contract >= ?'
        params.append(start_from)
    if end_to:
        sql += ' AND a.End_contract <= ?'
        params.append(end_to)
    if location:
        sql += ' AND LTRIM(RTRIM(a.Contract_swu_location_name)) = ?'
        params.append(location)
    if name:
        sql += ' AND cu.CompanyName LIKE ?'
        params.append(_to_sql_like_pattern(name))
    sql += ' ORDER BY a.Contract_code, a.Contract_Installment_month_year, a.Contract_Installment_seq'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_invoice_documents(keys):
    """
    ข้อมูลพิมพ์ใบแจ้งหนี้จาก sp_6000_Contact_Doc_invoice ทีละใบ

    keys -- [(contract_id, fi_doc), ...] ตามลำดับที่ต้องการพิมพ์
    คืน [{'contract_id', 'fi_doc', 'header': แถวแรกของ SP, 'lines': [แถว...], 'total'}, ...]
    ใบที่ SP ไม่คืนแถว (เลขไม่ตรงกัน/ถูกลบไปแล้ว) ถูกข้าม
    """
    documents = OrderedDict()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for contract_id, fi_doc in keys:
            cursor.execute(
                'EXEC dbo.sp_6000_Contact_Doc_invoice @p_Contract_id = ?, @p_Contract_fi_doc = ?',
                str(contract_id), str(fi_doc),
            )
            if cursor.description is None:
                continue
            columns = [c[0] for c in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if not rows:
                continue
            documents[(str(contract_id), str(fi_doc))] = {
                'contract_id': str(contract_id),
                'fi_doc': str(fi_doc),
                'header': rows[0],
                'lines': rows,
                'total': sum((row.get('Contract_Installment_amt') or 0) for row in rows),
            }
    finally:
        conn.close()
    return list(documents.values())
