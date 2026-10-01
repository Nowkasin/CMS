# meters/services/termination.py
from .db import get_db_connection
from .meters import _to_sql_like_pattern

# สถานะสัญญาที่ยกเลิกซ้ำไม่ได้ (อ้างจาก dbo.Contract_status_ms)
#   '4' ไม่ต่อสัญญา / '5' ยกเลิกสัญญา -> เป็นผลลัพธ์ของการยกเลิกอยู่แล้ว
#   '9' ปิดสัญญา                       -> ปิดจบแล้ว
# ค่าชุดเดียวกันนี้ถูกบังคับใน sp_Contract_Termination_Save ด้วย (เป็นด่านจริง)
# ที่นี่ใช้เพื่อ "ปิดฟอร์มล่วงหน้า" ให้ผู้ใช้รู้ก่อนกรอก ไม่ใช่กรอกเสร็จแล้วเพิ่งโดนปฏิเสธ
BLOCKED_CONTRACT_STATUSES = frozenset({'4', '5', '9'})

# จำกัดผลค้นหา -- พิมพ์คำกว้างๆ อย่าง "บริษัท" เดิมคืนมาเป็นร้อยแถวรวดเดียว
SEARCH_RESULT_LIMIT = 50


def find_contract_for_termination(search):
    """
    ค้นหาสัญญาสำหรับหน้ายกเลิกสัญญา -- รองรับค้นหาบางส่วนของรหัสสัญญา หรือชื่อบริษัทลูกค้า
    (เผื่อผู้ใช้จำรหัสสัญญาเป๊ะๆ ไม่ได้) คืนค่าเป็น list of dict เสมอ
    -- ถ้าเจอ 1 รายการ view จะ redirect ตรงเข้าไปเลย, ถ้าเจอหลายรายการให้โชว์ลิสต์เลือก

    คืนสถานะสัญญา (Status_contract_Desc) + ธงว่ามีข้อมูลยกเลิกแล้วหรือยัง (Has_termination)
    มาด้วย เพื่อให้หน้าค้นหาบอกได้ตั้งแต่ในลิสต์ว่าสัญญาไหนยกเลิกไปแล้ว
    ไม่ต้องให้ผู้ใช้คลิกเข้าไปเจอทางตันเอง

    ดึงเกินลิมิตมา 1 แถวเพื่อให้ view รู้ว่า "ยังมีอีก" แล้วเตือนให้พิมพ์ให้แคบลง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # escape wildcard ที่ผู้ใช้พิมพ์มาจริง (% _ [) ไม่ให้ถูกตีความเป็น wildcard ของ SQL
        # ไม่งั้นค้นหา '%' จะคืนสัญญาทั้งหมดในระบบ
        like = _to_sql_like_pattern(search)
        cursor.execute(
            """
            SELECT TOP (?)
                   c.Contract_id, c.Contract_code, c.Status_contract_id,
                   s.Status_contract_Desc, cu.CompanyName,
                   CAST(CASE WHEN t.Contract_id IS NULL THEN 0 ELSE 1 END AS int) AS Has_termination
            FROM dbo.Contract_hrd_tr c
            LEFT JOIN dbo.Contract_status_ms s ON s.Status_contract_id = c.Status_contract_id
            LEFT JOIN dbo.Contract_termination_tr t ON t.Contract_id = c.Contract_id
            -- Contract_customer_tr.Contract_id เป็น nvarchar(50) ส่วน Contract_hrd_tr.Contract_id
            -- เป็น int -- join ตรงๆ จะเป็น implicit convert ที่พังทั้ง query ถ้ามีแถวไหน
            -- เก็บข้อความที่ไม่ใช่ตัวเลข จึงใช้ TRY_CONVERT + OUTER APPLY TOP 1
            -- (TOP 1 กันแถวงอกด้วย เผื่อวันหน้ามีลูกค้าหลายแถวต่อสัญญา)
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = c.Contract_id
            ) cu
            WHERE LTRIM(RTRIM(c.Contract_code)) LIKE ? OR cu.CompanyName LIKE ?
            ORDER BY c.Contract_code, c.Contract_id
            """,
            SEARCH_RESULT_LIMIT + 1, like, like,
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_contract_summary(contract_id):
    """
    ข้อมูลระบุตัวสัญญาสำหรับหัวหน้า termination_detail -- รหัสสัญญา ชื่อลูกค้า สถานะปัจจุบัน

    จำเป็นเพราะหน้านี้บันทึกได้ครั้งเดียวและแก้ไม่ได้ แต่เดิมหัวหน้าขึ้นแค่
    "Contract_id #1" ผู้ใช้ไม่มีทางรู้ว่าเข้าสัญญาถูกตัวหรือเปล่าก่อนกดบันทึก

    คืน None ถ้าไม่พบสัญญา -> view จะตอบ 404 แทนการโชว์ฟอร์มเปล่าที่กดบันทึกแล้วพัง
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.Contract_id, c.Contract_code, c.Contract_year,
                   c.Status_contract_id, s.Status_contract_Desc,
                   c.Contract_signer_date_swu, c.Contract_target_desc,
                   cu.CompanyName, cu.Vendor_tel
            FROM dbo.Contract_hrd_tr c
            LEFT JOIN dbo.Contract_status_ms s ON s.Status_contract_id = c.Status_contract_id
            OUTER APPLY (
                SELECT TOP 1 x.CompanyName, x.Vendor_tel
                FROM dbo.Contract_customer_tr x
                WHERE TRY_CONVERT(int, x.Contract_id) = c.Contract_id
            ) cu
            WHERE c.Contract_id = ?
            """,
            contract_id,
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [c[0] for c in cursor.description]
        return dict(zip(columns, row))
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


_SP_SET_SELECTION = """
    EXEC dbo.sp_Contract_Termination_SetInstallmentSelection
        @Termination_id     = ?,
        @Installment_period = ?,
        @Is_selected        = ?,
        @UserId             = ?
"""


def set_installment_selection(termination_id, installment_period, is_selected, user_id):
    """เรียก sp_Contract_Termination_SetInstallmentSelection -- ติ๊กเลือก/ยกเลิกงวดเดียว"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            _SP_SET_SELECTION,
            termination_id, installment_period, 1 if is_selected else 0, user_id,
        )
        conn.commit()
    finally:
        conn.close()


def set_all_installment_selections(termination_id, is_selected, user_id):
    """
    ติ๊ก/ยกเลิกงวดทั้งหมดของการยกเลิกสัญญานี้ในคราวเดียว

    เดิมผู้ใช้ต้องกดทีละงวด ซึ่งแต่ละครั้งคือ 1 request + reload หน้าใหม่
    กรณีผ่อนผัน 2 เดือนอาจมีงวดถึง 25 งวด (ขอบเขตที่ SP จำกัดไว้)

    ยังเรียกผ่าน SP เดิมทีละงวด (ไม่เขียน UPDATE ตรงเข้าตาราง เพื่อคงสถาปัตยกรรมที่
    การเขียนข้อมูลผ่าน stored procedure เท่านั้น) แต่ใช้ connection เดียวและ commit
    ครั้งเดียวตอนท้าย -- ถ้างวดใดพลาด จะ rollback ทั้งชุด ไม่เหลือสถานะครึ่งๆ กลางๆ

    คืนจำนวนงวดที่อัปเดต
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT Installment_period
            FROM dbo.Contract_termination_installment_dt
            WHERE Termination_id = ?
            ORDER BY Installment_period
            """,
            termination_id,
        )
        periods = [row[0] for row in cursor.fetchall()]

        flag = 1 if is_selected else 0
        for period in periods:
            cursor.execute(_SP_SET_SELECTION, termination_id, period, flag, user_id)

        conn.commit()
        return len(periods)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()