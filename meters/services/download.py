# meters/services/download.py
"""
บริการสำหรับหน้าดาวน์โหลด Excel รายชื่อสัญญา + เลขอ่านมิเตอร์น้ำ/ไฟตามรอบบิลที่เลือก

ไม่ใช้ SP_4000_Getlist_HRD_TR_CMS เพราะ SP นั้นบังคับกรองด้วย @p_user = UserEntry ของคนกรอกสัญญา
(ยังไม่แกะ K2 ยังไม่มี user login จริงให้ส่งเข้าไป) ใช้ query ตรงแทนไปก่อน ดึงสัญญา active ทั้งหมด
(Status_contract_id NOT IN (5,9)) ไม่กรอง user -- ทีหลังพอแกะ K2 เสร็จค่อยเปลี่ยนมาเรียก SP จริง

สำคัญ: Contract_Installment_tr_dt.Contract_meter_id เป็นเลขมิเตอร์ของระบบ Installment เดิมของ
มหาลัย ไม่ใช่ Meter_id/Meter_no ของ Contract_meter_ms ในระบบ CMS นี้ (คนละระบบ ไม่เชื่อมกัน --
ยืนยันแล้วจากการตรวจสอบจริง) จึงจับคู่เลขอ่าน/จำนวนเงินกับสัญญาผ่าน Contract_id +
Contract_type_price_id (8=ไฟ, 9=น้ำ) + เดือน-ปีของ Contract_effective_date เท่านั้น ไม่ join
ผ่าน meter_id
"""
from .db import get_db_connection


def fetch_contracts_for_download(meter_type_cd, billing_year_be, billing_month):
    """
    ดึงรายชื่อสัญญา active ทั้งหมดที่มีมิเตอร์ประเภทที่ระบุ (9=น้ำ, 8=ไฟ) ผูกอยู่ พร้อมเลขอ่าน
    ก่อน-หลัง/จำนวนเงินของรอบบิลที่เลือก (LEFT JOIN -- ถ้าไม่มีงวดของเดือนนี้ แถวยังอยู่
    แต่เลขอ่าน/จำนวนเงินจะเป็น NULL ไม่ถูกตัดทิ้ง)

    ลำดับพื้นที่ย่อย/ลำดับมิเตอร์ WW_seq/EE_seq ไม่รู้ logic การนับจริงของมหาลัย (ยืนยันกับ
    ผู้ใช้แล้วว่าไม่รู้เหมือนกัน) คำนวณเองที่ views/download.py จากลำดับที่ query เจอ
    (ORDER BY Contract_id, Meter_id) ไม่ใช่ค่าจาก DB โดยตรง -- ต้องปรับถ้าไม่ตรงกับที่ต้องการ
    """
    ad_year = billing_year_be - 543

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.Contract_id,
                c.Contract_code,
                c.Contract_year,
                c.Contract_grouping,
                cu.Customer_id,
                cu.TaxNumber,
                cu.CompanyName,
                mt.Location_id,
                loc.Location_name,
                mt.Area_id,
                am.Area_name,
                mt.SubArea_id,
                sam.SubArea_name,
                m.Meter_id,
                m.Meter_no,
                m.Phase_type,
                dt.Contract_read_number_before,
                dt.Contract_read_number_after,
                dt.Contract_effective_date,
                it.Contract_Installment_amt
            FROM dbo.Contract_hrd_tr c
            JOIN dbo.Contract_meter_tr mt ON mt.Contract_id = c.Contract_id AND mt.UseOrNot = 1
            JOIN dbo.Contract_meter_ms m ON m.Meter_id = mt.Meter_id AND m.Meter_type_cd = ?
            LEFT JOIN dbo.Contract_customer_tr cu ON cu.Contract_id = c.Contract_id
            LEFT JOIN dbo.Contract_location_ms loc ON loc.Location_id = mt.Location_id
            LEFT JOIN dbo.Contract_location_area_ms am ON am.Area_id = mt.Area_id
            LEFT JOIN dbo.Contract_location_subarea_ms sam ON sam.SubArea_id = mt.SubArea_id
            LEFT JOIN dbo.Contract_Installment_tr_dt dt
                ON dt.Contract_id = c.Contract_id
                AND dt.Contract_type_price_id = ?
                AND YEAR(dt.Contract_effective_date) = ?
                AND MONTH(dt.Contract_effective_date) = ?
            LEFT JOIN dbo.Contract_Installment_tr it
                ON it.Contract_id = dt.Contract_id
                AND it.Contract_Installment_seq = dt.Contract_Installment_seq
            WHERE c.Status_contract_id NOT IN (5, 9)
            ORDER BY c.Contract_id, m.Meter_id
            """,
            meter_type_cd, meter_type_cd, ad_year, billing_month,
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()