# meters/services/download.py

from .db import get_db_connection

METER_TYPE_TO_PRICE_TYPE = {
    9: '8',   # มิเตอร์น้ำ   -> ค่าน้ำประปา
    8: '9',   # มิเตอร์ไฟฟ้า -> ค่าไฟฟ้า
}


def fetch_contracts_for_download(meter_type_cd, billing_year_be, billing_month):
    """
    ดึงรายการ (สัญญา x พื้นที่ย่อย x มิเตอร์) ของสัญญา active ทั้งหมดที่มีมิเตอร์ประเภทที่ระบุ
    (9=น้ำ, 8=ไฟ) ผูกอยู่ พร้อมเลขอ่านก่อน-หลัง/จำนวนเงินของรอบบิลที่เลือก (LEFT JOIN -- ถ้าไม่มี
    งวดของเดือนนี้ แถวยังอยู่แต่เลขอ่าน/จำนวนเงิน/Base Line Date จะเป็น NULL ไม่ถูกตัดทิ้ง)

    meter_type_cd รับได้แค่ 9 (น้ำ) หรือ 8 (ไฟฟ้า) -- ค่าอื่นจะ raise ValueError ทันที
    ไม่ปล่อยให้ query ผ่านไปแล้วคืนลิสต์ว่างเงียบๆ ซึ่งแยกไม่ออกจาก "ไม่มีข้อมูลในรอบบิลนี้"

    ลำดับมิเตอร์ WW_seq/EE_seq ไม่มีคอลัมน์จริงรองรับ (ยืนยันกับผู้ใช้แล้วว่าไม่รู้ logic) คำนวณเอง
    ที่ views/download.py จากลำดับที่ query เจอต่อสัญญาเดียวกัน -- ต้องปรับถ้าไม่ตรงกับที่ต้องการ
    ส่วนลำดับพื้นที่ย่อยใช้ Contract_Location_area_tr.Contract_Location_seq ตรงๆ (มีคอลัมน์จริง)
    """
    try:
        meter_type_cd = int(meter_type_cd)
    except (TypeError, ValueError):
        raise ValueError(f"meter_type_cd ต้องเป็น 9 (น้ำ) หรือ 8 (ไฟฟ้า) ได้รับ: {meter_type_cd!r}")
    if meter_type_cd not in METER_TYPE_TO_PRICE_TYPE:
        raise ValueError(f"meter_type_cd ต้องเป็น 9 (น้ำ) หรือ 8 (ไฟฟ้า) ได้รับ: {meter_type_cd!r}")

    price_type_id = METER_TYPE_TO_PRICE_TYPE[meter_type_cd]
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
                cu.Customer_id,
                cu.TaxNumber,
                cu.CompanyName,
                la.Contract_Location_seq,
                la.Location_id,
                loc.Location_name,
                la.Area_id,
                am.Area_name,
                la.SubArea_id,
                la.Contract_area_desc,
                st.Status_contract_Desc,
                m.Meter_id,
                m.Meter_no,
                m.Phase_type,
                dt.Contract_read_number_before,
                dt.Contract_read_number_after,
                dt.Contract_effective_date,
                it.Contract_Installment_amt,
                it.Contract_duedate
            FROM dbo.Contract_hrd_tr c
            JOIN dbo.Contract_Location_area_tr la ON la.Contract_id = c.Contract_id
            JOIN dbo.Contract_meter_tr mt
                ON mt.Contract_id = c.Contract_id
                AND mt.SubArea_id = la.SubArea_id
                AND mt.UseOrNot = 1
            JOIN dbo.Contract_meter_ms m ON m.Meter_id = mt.Meter_id AND m.Meter_type_cd = ?
            LEFT JOIN dbo.Contract_customer_tr cu ON cu.Contract_id = c.Contract_id
            LEFT JOIN dbo.Contract_location_ms loc ON loc.Location_id = la.Location_id
            LEFT JOIN dbo.Contract_location_area_ms am
                ON am.Location_id = la.Location_id AND am.Area_id = la.Area_id
            LEFT JOIN dbo.Contract_status_ms st ON st.Status_contract_id = c.Status_contract_id
            -- dt.Contract_type_price_id ใช้รหัส "ประเภทค่าใช้จ่าย" ซึ่งสลับกับ Meter_type_cd
            -- จึงต้องส่ง price_type_id ที่แปลงผ่าน METER_TYPE_TO_PRICE_TYPE มาแล้ว
            -- ห้ามส่ง meter_type_cd ตรงๆ (ดูคอมเมนต์หัวไฟล์)
            LEFT JOIN dbo.Contract_Installment_tr_dt dt
                ON dt.Contract_id = c.Contract_id
                AND dt.Contract_type_price_id = ?
                AND YEAR(dt.Contract_effective_date) = ?
                AND MONTH(dt.Contract_effective_date) = ?
            LEFT JOIN dbo.Contract_Installment_tr it
                ON it.Contract_id = dt.Contract_id
                AND it.Contract_Installment_seq = dt.Contract_Installment_seq
            -- Status_contract_id เป็น nvarchar(2) -- ต้องเทียบกับสตริง ไม่ใช่ตัวเลข
            -- เดิมเขียน NOT IN (5, 9) ซึ่งบังคับให้ SQL Server แปลงคอลัมน์เป็น int ทั้งคอลัมน์
            -- ค่าปัจจุบันเป็นตัวเลขทั้งหมดจึงยังไม่พัง แต่ถ้ามีค่าอย่าง 'A1' เข้ามาแถวเดียว
            -- query จะล้มทั้ง query ("Conversion failed ... to data type int") ทำให้หน้าดาวน์โหลดใช้ไม่ได้
            -- ยืนยันแล้วว่าสองรูปแบบคืนสัญญาชุดเดียวกันเป๊ะ (223 แถว ไม่มีแถวต่าง)
            --
            -- หมายเหตุ: ตั้งใจไม่ตัดสถานะ '4' (ไม่ต่อสัญญา) ออก เพราะ case 2 ของการยกเลิกสัญญา
            -- ให้ผ่อนผัน 1 เดือน จึงยังต้องส่งงวดสุดท้ายออกไปตั้งหนี้
            WHERE c.Status_contract_id NOT IN ('5', '9')
            ORDER BY c.Contract_id, la.Contract_Location_seq, m.Meter_id
            """,
            # พารามิเตอร์ตัวที่ 1 = ประเภทมิเตอร์ (int) / ตัวที่ 2 = ประเภทค่าใช้จ่าย (str)
            # เป็นค่าต่างกัน ไม่ใช่ตัวเดียวกันอย่างที่เคยเขียนไว้
            meter_type_cd, price_type_id, ad_year, billing_month,
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()