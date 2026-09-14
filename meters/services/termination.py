# meters/services/termination.py
from .db import get_db_connection


def find_contract_for_termination(search):
    """
    ค้นหาสัญญาสำหรับหน้ายกเลิกสัญญา -- รองรับค้นหาบางส่วนของรหัสสัญญา หรือชื่อบริษัทลูกค้า
    (เผื่อผู้ใช้จำรหัสสัญญาเป๊ะๆ ไม่ได้) คืนค่าเป็น list of dict เสมอ
    -- ถ้าเจอ 1 รายการ view จะ redirect ตรงเข้าไปเลย, ถ้าเจอหลายรายการให้โชว์ลิสต์เลือก
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        like = f"%{search}%"
        cursor.execute(
            """
            SELECT DISTINCT c.Contract_id, c.Contract_code, c.Status_contract_id, cu.CompanyName
            FROM dbo.Contract_hrd_tr c
            LEFT JOIN dbo.Contract_customer_tr cu ON cu.Contract_id = c.Contract_id
            WHERE LTRIM(RTRIM(c.Contract_code)) LIKE ? OR cu.CompanyName LIKE ?
            ORDER BY c.Contract_code
            """,
            like, like,
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def save_termination(contract_id, contract_code, termination_case, contract_end_date,
                      notify_date, remark, user_id):
    """
    เรียก sp_Contract_Termination_Save -- ยืนยัน parameter ครบ 7 ตัวจาก schema จริงแล้ว:
    @Contract_id, @Contract_code, @Termination_case, @Contract_end_date,
    @Notify_date, @Remark, @UserId (เดิมลืมใส่ @Contract_code ไปตัวหนึ่ง)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_Contract_Termination_Save
                @Contract_id       = ?,
                @Contract_code     = ?,
                @Termination_case  = ?,
                @Contract_end_date = ?,
                @Notify_date       = ?,
                @Remark            = ?,
                @UserId            = ?
            """,
            contract_id, contract_code, termination_case, contract_end_date, notify_date, remark, user_id,
        )
        row = cursor.fetchone()
        columns = [c[0] for c in cursor.description] if cursor.description else []
        result = dict(zip(columns, row)) if row else None
        conn.commit()
        return result
    finally:
        conn.close()


def fetch_termination_detail(contract_id=None, contract_code=None):
    """
    เรียก sp_Contract_Termination_SelectByContract -- SP นี้คืน 2 result set
    (หัวข้อมูลยกเลิก + รายการงวด) ต้องใช้ cursor.nextset() ไล่อ่านทีละชุด
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "EXEC dbo.sp_Contract_Termination_SelectByContract @Contract_id = ?, @Contract_code = ?",
            contract_id, contract_code,
        )
        header = None
        if cursor.description:
            columns = [c[0] for c in cursor.description]
            row = cursor.fetchone()
            header = dict(zip(columns, row)) if row else None

        periods = []
        if cursor.nextset() and cursor.description:
            columns2 = [c[0] for c in cursor.description]
            periods = [dict(zip(columns2, r)) for r in cursor.fetchall()]

        return header, periods
    finally:
        conn.close()


def set_installment_selection(termination_id, installment_period, is_selected, user_id):
    """เรียก sp_Contract_Termination_SetInstallmentSelection -- ติ๊กเลือก/ยกเลิกงวด"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC dbo.sp_Contract_Termination_SetInstallmentSelection
                @Termination_id     = ?,
                @Installment_period = ?,
                @Is_selected        = ?,
                @UserId             = ?
            """,
            termination_id, installment_period, 1 if is_selected else 0, user_id,
        )
        conn.commit()
    finally:
        conn.close()