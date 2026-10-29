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

    --- แหล่งที่มาของเลขอ่านก่อน-หลัง (เปลี่ยนแล้ว) ---
    เดิมอ่านจาก Contract_Installment_tr_dt ซึ่งผูกด้วย สัญญา + ประเภทค่าใช้จ่าย + เดือน
    ไม่ผูกกับมิเตอร์ ส่วนระบบนำเข้า Excel และหน้าแก้ไขมิเตอร์เขียนเลขอ่านลง
    Contract_meter_reading_tr (คีย์ Meter_id + Billing_year_be + Billing_month) ผลคือเลขที่เพิ่ง
    นำเข้าไม่ขึ้นในหน้าดาวน์โหลด/ไฟล์ที่ออกไป ตอนนี้ join ตารางใหม่ด้วย Meter_id ตรงๆ
    (unique ต่อมิเตอร์ต่อรอบบิล จึงไม่ทำให้แถวเพิ่ม) แล้วเลือกใช้ตามนี้:
      - มีแถวในตารางใหม่ของมิเตอร์นี้ในรอบบิลนี้ -> ใช้ค่า "ทั้งคู่" จากตารางใหม่ (ถ้าช่องไหนว่างก็ว่าง
        ไม่ดึงอีกฝั่งจากตารางเก่ามาผสม เพราะจะได้คู่ก่อน/หลังที่มาจากคนละที่)
      - ไม่มีแถวในตารางใหม่ -> ใช้ค่าจากตารางเดิมเหมือนที่เคยเป็น (รอบบิลเก่าก่อนมีระบบใหม่ยังเห็นข้อมูล)
    เลือกใน Python ไม่ใช้ CASE/COALESCE ใน SQL เพราะไม่ทราบว่าสองตารางเก็บเลขอ่านเป็นชนิดเดียวกัน
    หรือไม่ -- ถ้าชนิดต่างกัน SQL Server จะพยายามแปลงทั้งคอลัมน์แล้วอาจล้มทั้ง query

    ส่วน "วันที่อ่านเลขมิเตอร์" (Contract_effective_date), จำนวนเงิน และวันครบกำหนด ยังมาจากตารางงวดเดิม
    เพราะตารางเลขอ่านใหม่ไม่มีคอลัมน์เหล่านี้
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
                -- เลขอ่านจากตารางใหม่ (Contract_meter_reading_tr) -- เลือกใช้ใน Python ด้านล่าง
                rd.Meter_id AS Reading_meter_id,
                rd.Reading_before AS New_read_before,
                rd.Reading_after AS New_read_after,
                -- เลขอ่านจากตารางงวดเดิม (fallback เมื่อไม่มีแถวในตารางใหม่)
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
            -- เลขอ่านของมิเตอร์ตัวนี้ในรอบบิลที่เลือก -- มี unique (Meter_id, Billing_year_be,
            -- Billing_month) จึงได้ไม่เกิน 1 แถวต่อมิเตอร์ ไม่ทำให้ผลลัพธ์งอกแถว
            -- (ปีเป็น พ.ศ. ตรงๆ ไม่ต้องแปลง -- ต่างจากตารางงวดเดิมที่ต้องใช้ ค.ศ. ด้านล่าง)
            LEFT JOIN dbo.Contract_meter_reading_tr rd
                ON rd.Meter_id = m.Meter_id
                AND rd.Billing_year_be = ?
                AND rd.Billing_month = ?
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
            # ลำดับพารามิเตอร์ต้องตรงกับ ? ตามตำแหน่งที่ปรากฏใน SQL:
            #   1) ประเภทมิเตอร์ (int)  2-3) รอบบิลของตารางเลขอ่านใหม่ (พ.ศ., เดือน)
            #   4) ประเภทค่าใช้จ่าย (str)  5-6) รอบบิลของตารางงวดเดิม (ค.ศ., เดือน)
            meter_type_cd,
            billing_year_be, billing_month,
            price_type_id, ad_year, billing_month,
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

    # เลือกแหล่งเลขอ่านต่อแถว: มีแถวในตารางใหม่ -> ใช้คู่ก่อน/หลังจากตารางใหม่ทั้งคู่
    # ไม่มี -> คงค่าจากตารางงวดเดิม (ชื่อคีย์ Contract_read_number_* เดิม view/เทมเพลตจึงไม่ต้องแก้)
    for r in rows:
        has_new = r.pop('Reading_meter_id') is not None
        new_before = r.pop('New_read_before')
        new_after = r.pop('New_read_after')
        if has_new:
            r['Contract_read_number_before'] = new_before
            r['Contract_read_number_after'] = new_after
            r['Reading_source'] = 'reading_tr'
        else:
            r['Reading_source'] = 'installment'
    return rows