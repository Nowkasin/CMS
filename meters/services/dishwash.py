"""
ค่าล้างจานรายเดือนต่อสัญญา (dbo.Contract_dishwash_tr -- ติดตั้งด้วย deploy/2026-12-dishwash-fee)

- 1 แถวต่อสัญญาต่อรอบบิล (UNIQUE Contract_id + Billing_year_be + Billing_month) ผู้ใช้กรอกยอดเอง
- แถวที่ตั้งหนี้ SAP แล้ว (Contract_fi_doc มีค่า) ห้ามแก้/ลบจาก CMS -- ยอดต้องตรงกับเอกสาร SAP
- ล้างช่องยอดเงินแล้วบันทึก = ลบแถวของรอบนั้น (เฉพาะที่ยังไม่ตั้งหนี้)
- งานตั้งหนี้ SAP / ใบเสร็จ เขียนคอลัมน์ Contract_fi_doc ฯลฯ จากระบบอื่น หน้านี้อ่านอย่างเดียว
"""
from decimal import Decimal

from .db import get_db_connection
from .sql_utils import _to_sql_like_pattern
from .termination import BLOCKED_CONTRACT_STATUSES

DISHWASH_PRICE_TYPE = '11'          # Contract_type_price_ms: 11 ค่าล้างจาน
MAX_DISHWASH_AMOUNT = Decimal('9999999.99')
MAX_DISHWASH_REMARK_LEN = 500       # Remark nvarchar(500)


def fetch_dishwash_month(billing_year_be, billing_month, search=''):
    """
    รายการสัญญาสำหรับกรอกค่าล้างจานของรอบบิลหนึ่ง

    แสดงสัญญาที่ยังใช้งานได้ (สถานะไม่ใช่ ไม่ต่อสัญญา / ยกเลิก / ปิดสัญญา -- ชุดเดียวกับหน้ายกเลิกสัญญา)
    รวมสัญญาสถานะอื่นที่มีค่าล้างจานรอบนี้อยู่แล้ว เพื่อไม่ให้ยอดที่บันทึกไว้หายจากหน้าจอ
    """
    blocked = sorted(BLOCKED_CONTRACT_STATUSES)
    sql = f"""
        SELECT c.Contract_id, LTRIM(RTRIM(c.Contract_code)) AS Contract_code, c.Contract_year,
               c.Status_contract_id, s.Status_contract_Desc, cu.CompanyName,
               d.Dishwash_id, d.Amount, d.Remark, d.Contract_fi_doc, d.Contract_fi_date,
               COALESCE(d.UserUpdate, d.UserEntry) AS Saved_by,
               COALESCE(d.DateUpdate, d.DateEntry) AS Saved_at
        FROM dbo.Contract_hrd_tr c
        LEFT JOIN dbo.Contract_status_ms s ON s.Status_contract_id = c.Status_contract_id
        LEFT JOIN dbo.Contract_dishwash_tr d
               ON d.Contract_id = c.Contract_id AND d.Billing_year_be = ? AND d.Billing_month = ?
        OUTER APPLY (
            SELECT TOP 1 x.CompanyName
            FROM dbo.Contract_customer_tr x
            WHERE TRY_CONVERT(int, x.Contract_id) = c.Contract_id
        ) cu
        WHERE (ISNULL(c.Status_contract_id, '') NOT IN ({', '.join('?' * len(blocked))})
               OR d.Dishwash_id IS NOT NULL)
    """
    params = [int(billing_year_be), int(billing_month), *blocked]
    search = (search or '').strip()
    if search:
        like = _to_sql_like_pattern(search)
        sql += ' AND (LTRIM(RTRIM(c.Contract_code)) LIKE ? OR cu.CompanyName LIKE ?)'
        params += [like, like]
    sql += ' ORDER BY c.Contract_code, c.Contract_id'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def save_dishwash_month(billing_year_be, billing_month, entries, user_id):
    """
    บันทึกยอดค่าล้างจานหลายสัญญาของรอบบิลเดียวในทรานแซกชันเดียว (ล้มทั้งชุดถ้ามี error)

    entries: [{'contract_id': int, 'amount': Decimal | None, 'remark': str}]
      amount None = ลบแถวของรอบนั้น (ถ้ามี)
    คืน {'created': [...], 'updated': [...], 'deleted': [...], 'locked': [...]}
      แต่ละรายการเป็น {'contract_id', 'contract_code', 'amount'}
      locked = ตั้งหนี้ SAP แล้ว ไม่ได้แก้ (ไม่นับเป็น error)
    สัญญาที่ยอดและหมายเหตุไม่เปลี่ยน ไม่ถูกเขียนซ้ำ (UserUpdate/DateUpdate ไม่ขยับ)
    """
    result = {'created': [], 'updated': [], 'deleted': [], 'locked': []}
    if not entries:
        return result

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for entry in entries:
            contract_id = int(entry['contract_id'])
            amount = entry.get('amount')
            remark = (entry.get('remark') or '').strip() or None

            cursor.execute(
                """
                SELECT d.Dishwash_id, d.Amount, d.Remark, d.Contract_fi_doc,
                       LTRIM(RTRIM(c.Contract_code)) AS Contract_code
                FROM dbo.Contract_hrd_tr c
                LEFT JOIN dbo.Contract_dishwash_tr d WITH (UPDLOCK, HOLDLOCK)
                       ON d.Contract_id = c.Contract_id AND d.Billing_year_be = ? AND d.Billing_month = ?
                WHERE c.Contract_id = ?
                """,
                int(billing_year_be), int(billing_month), contract_id,
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f'ไม่พบสัญญา Contract_id {contract_id}')
            dishwash_id, old_amount, old_remark, fi_doc, contract_code = row
            item = {'contract_id': contract_id, 'contract_code': contract_code, 'amount': amount}

            if dishwash_id is None:
                if amount is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO dbo.Contract_dishwash_tr (
                        Contract_id, Contract_code, Billing_year_be, Billing_month, Amount, Remark,
                        Contract_debt_to_SAP, UserEntry, DateEntry
                    )
                    VALUES (?, ?, ?, ?, ?, ?, N'0', ?, GETDATE())
                    """,
                    contract_id, contract_code, int(billing_year_be), int(billing_month),
                    amount, remark, user_id,
                )
                result['created'].append(item)
                continue

            unchanged = (amount is not None and old_amount is not None
                         and Decimal(old_amount) == amount and (old_remark or None) == remark)
            if unchanged:
                continue
            if fi_doc:
                result['locked'].append(dict(item, amount=old_amount))
                continue

            if amount is None:
                cursor.execute('DELETE FROM dbo.Contract_dishwash_tr WHERE Dishwash_id = ? AND Contract_fi_doc IS NULL',
                               dishwash_id)
                result['deleted'].append(dict(item, amount=old_amount))
            else:
                cursor.execute(
                    """
                    UPDATE dbo.Contract_dishwash_tr
                    SET Amount = ?, Remark = ?, UserUpdate = ?, DateUpdate = GETDATE()
                    WHERE Dishwash_id = ? AND Contract_fi_doc IS NULL
                    """,
                    amount, remark, user_id, dishwash_id,
                )
                result['updated'].append(dict(item, old_amount=old_amount))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
