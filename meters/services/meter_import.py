"""
นำเข้าข้อมูลมิเตอร์จากไฟล์ Excel ที่ staged ไว้ (Step 3 ของ wizard) และตัวเรียก SP
ที่ใช้เขียนทะเบียนมิเตอร์ / ผูกสัญญา / เลขอ่าน บน cursor ที่ผู้เรียกส่งมา (ไม่ commit เอง)
"""
from .activity_log import ACTION_UPLOAD_COMMIT, add_activity_log
from .db import get_db_connection


def sp_meter_save(cursor, location_id, area_id, subarea_id, type_cd, meter_no,
                   meter_no_status, user_id, logs, phase_type=None, meter_id=None,
                   meter_remark=None, use_or_not=1):
    """
    meter_id=None (ค่าเริ่มต้น) -> SP จะ INSERT มิเตอร์ใหม่ (ใช้ตอน import จากไฟล์ Excel)
    meter_id=<เลขจริง> -> SP จะ UPDATE มิเตอร์ตัวนั้นแทน (ใช้ตอนแก้ไขจากหน้า dashboard)

    use_or_not (default 1 = เปิดใช้งาน) -- ส่งต่อไป @UseOrNot ของ SP ตรงๆ ผู้เรียกเดิมที่ไม่ส่ง
    พารามิเตอร์นี้ยังทำงานเหมือนเดิมทุกอย่าง (SP มี default @UseOrNot = 1 อยู่แล้ว)
    """
    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_Save
            @Meter_id        = ?,
            @Location_id     = ?,
            @Area_id         = ?,
            @SubArea_id      = ?,
            @Meter_type_cd   = ?,
            @Meter_no        = ?,
            @Meter_no_status = ?,
            @Phase_type      = ?,
            @Meter_remark    = ?,
            @UseOrNot        = ?,
            @UserId          = ?
        """,
        meter_id, location_id, area_id, subarea_id, type_cd, meter_no, meter_no_status,
        phase_type, meter_remark, use_or_not, user_id
    )
    row = cursor.fetchone()
    result_meter_id = int(row[0]) if row else meter_id
    cls = 'water' if type_cd == 9 else 'electric'
    action = 'UPDATE' if meter_id else 'INSERT'
    logs.append((cls, f"EXEC sp_Contract_Meter_Save ({action})  @SubArea_id='{subarea_id}', "
                       f"@Meter_type_cd={type_cd}, @Meter_no={meter_no!r}  -> Meter_id={result_meter_id}"))
    return result_meter_id


def sp_bind_to_contract(cursor, contract_id, location_id, area_id, subarea_id, meter_id, user_id, logs):

    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_BindToContract
            @Contract_id   = ?,
            @Location_id   = ?,
            @Area_id       = ?,
            @SubArea_id    = ?,
            @Meter_id_list = ?,
            @UserId        = ?
        """,
        contract_id, location_id, area_id, subarea_id, str(meter_id), user_id
    )
    logs.append(('bind', f"EXEC sp_Contract_Meter_BindToContract  @Contract_id={contract_id}, "
                          f"@Meter_id_list='{meter_id}'"))


def sp_meter_reading_save(cursor, meter_id, billing_year_be, billing_month, reading_before,
                          reading_after, user_id, contract_id=None, contract_code=None):
    """
    เรียก sp_Contract_Meter_Reading_Save บน cursor ที่ส่งเข้ามา "โดยไม่ commit"
    คืนค่า Reading_id (None ถ้า SP ไม่คืนแถวผลลัพธ์)

    แยกออกมาจาก save_meter_reading() เพราะฟังก์ชันนั้นเปิด connection ของตัวเองและ commit
    ทันที -- ถ้า commit_staged_rows เรียกมันตรงๆ เลขอ่านจะ commit แยกจากการนำเข้ามิเตอร์
    ถ้าขั้นหลังพังจะเหลือเลขอ่านครึ่งๆ กลางๆ ฟังก์ชันนี้ใช้ cursor เดียวกับ sp_meter_save /
    sp_bind_to_contract จึงอยู่ใน transaction เดียวกันและ commit/rollback พร้อมกัน

    ปีส่งเป็น พ.ศ. ตรงๆ (คอลัมน์ Billing_year_be เก็บ พ.ศ.) -- ดูรายละเอียดใน save_meter_reading
    """
    if reading_before is not None and not isinstance(reading_before, int):
        raise ValueError(f"reading_before ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_before!r}")
    if reading_after is not None and not isinstance(reading_after, int):
        raise ValueError(f"reading_after ต้องเป็น int หรือ None เท่านั้น ได้รับ: {reading_after!r}")

    contract_id = int(contract_id) if contract_id else None
    contract_code = (str(contract_code).strip() or None) if contract_code else None

    cursor.execute(
        """
        EXEC dbo.sp_Contract_Meter_Reading_Save
            @Meter_id        = ?,
            @Billing_year_be = ?,
            @Billing_month   = ?,
            @Reading_before  = ?,
            @Reading_after   = ?,
            @UserId          = ?,
            @Contract_id     = ?,
            @Contract_code   = ?
        """,
        int(meter_id), billing_year_be, billing_month,
        reading_before, reading_after, user_id, contract_id, contract_code,
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def find_existing_meter(cursor, subarea_id, meter_type_cd, meter_no):
    """
    หามิเตอร์ที่ลงทะเบียนไว้แล้วในพื้นที่นี้ เพื่อใช้ Meter_id เดิมซ้ำแทนการสร้างแถวใหม่
    คืนค่า (Meter_id, Meter_no, Meter_no_status) หรือ None ถ้าไม่เจอ

    ทำไมต้องมี: sp_Contract_Meter_Save จะ INSERT ใหม่ทุกครั้งที่ @Meter_id เป็น NULL
    โดยไม่เช็คเลยว่าเลขเครื่องวัดนี้มีอยู่แล้วหรือยัง และ UQ_Contract_meter_ms ที่มีอยู่
    คุมแค่ (SubArea_id, Meter_type_cd, Meter_seq) ซึ่ง SP รันเลข seq ใหม่ให้ทุกครั้ง
    -> ไม่มีอะไรกันการซ้ำเลย อัปโหลดไฟล์เดิมซ้ำจึงได้มิเตอร์งอกเพิ่มทั้งชุด
    ผู้เรียกต้องหา Meter_id เดิมเองแล้วส่งเข้า SP เพื่อให้เข้า branch UPDATE

    การจับคู่:
      - มีเลขเครื่องวัด -> เทียบ (SubArea_id, Meter_type_cd, Meter_no) แบบ TRIM ทั้ง 2 ฝั่ง
      - ไม่มีเลข (แถว "รอ Gen เลข") -> เทียบ (SubArea_id, Meter_type_cd) และใช้ซ้ำเฉพาะตอน
        เจอตัวเดียวเท่านั้น เพราะถ้าเจอหลายตัวจะไม่รู้ว่าหมายถึงตัวไหน ปล่อยให้ INSERT ใหม่
    เทียบเฉพาะแถว UseOrNot = 1 -- มิเตอร์ที่ถูกปิดใช้งานไว้ไม่ควรถูกปลุกกลับมาโดยการ import
    """
    if meter_no:
        cursor.execute(
            """
            SELECT Meter_id, Meter_no, Meter_no_status
            FROM dbo.Contract_meter_ms
            WHERE LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
              AND Meter_type_cd = ?
              AND LTRIM(RTRIM(Meter_no)) = LTRIM(RTRIM(?))
              AND UseOrNot = 1
            ORDER BY Meter_id
            """,
            subarea_id, meter_type_cd, meter_no,
        )
        row = cursor.fetchone()
        return (row[0], row[1], row[2]) if row else None

    cursor.execute(
        """
        SELECT Meter_id, Meter_no, Meter_no_status
        FROM dbo.Contract_meter_ms
        WHERE LTRIM(RTRIM(SubArea_id)) = LTRIM(RTRIM(?))
          AND Meter_type_cd = ?
          AND UseOrNot = 1
        ORDER BY Meter_id
        """,
        subarea_id, meter_type_cd,
    )
    found = cursor.fetchall()
    if len(found) == 1:
        r = found[0]
        return (r[0], r[1], r[2])
    return None


class ImportRowError(Exception):
    """
    แถวหนึ่งบันทึกลงฐานข้อมูลไม่สำเร็จระหว่าง commit_staged_rows -- ทั้งไฟล์ถูก rollback แล้ว

    เก็บแค่ข้อมูลระบุแถว ข้อความ error ดิบจาก pyodbc อยู่ใน __cause__ ให้ผู้เรียกเขียนลง
    logger ของเซิร์ฟเวอร์ ไม่แสดงบนหน้าเว็บ (มีชื่อตาราง/driver ติดมา)
    """

    def __init__(self, row_idx, subarea_id, type_label=None):
        self.row_idx = row_idx
        self.subarea_id = subarea_id
        self.type_label = type_label
        super().__init__(f'import row {row_idx} (SubArea {subarea_id}) failed')

    def user_message(self):
        kind = f'มิเตอร์{self.type_label} ' if self.type_label else ''
        return (
            f'บันทึกแถวที่ {self.row_idx} ({kind}พื้นที่ย่อย {self.subarea_id}) ไม่สำเร็จ '
            f'-- เกิดข้อผิดพลาดจากระบบฐานข้อมูล ระบบยกเลิกการนำเข้าทั้งไฟล์แล้ว '
            f'(ยังไม่มีข้อมูลใดถูกบันทึก) กรุณาตรวจสอบแถวนี้ หรือติดต่อผู้ดูแลระบบ'
        )


def commit_staged_rows(rows, user_id, source_filename=None, billing_period=None,
                       billing_month=None, billing_year_be=None):
    """
    นำเข้าข้อมูลมิเตอร์จากไฟล์ Excel ที่ staged ไว้ลงฐานข้อมูลจริง

    source_filename / billing_period ใช้เขียน Contract_activity_log เท่านั้น
    (ชื่อไฟล์และรอบบิลมีอยู่แค่ใน session ฝั่ง Python ไม่มีใน DB) -- เป็น optional
    เพื่อให้ผู้เรียกเดิมที่ไม่ส่งมายังทำงานได้เหมือนเดิม

    billing_month (1-12) / billing_year_be (พ.ศ.) เป็นตัวเลข ใช้บันทึกเลขอ่านก่อน-หลังของแต่ละแถว
    ลง Contract_meter_reading_tr ผ่าน sp_Contract_Meter_Reading_Save ใน transaction เดียวกับ
    การนำเข้ามิเตอร์ -- ถ้าไม่ส่งมา (เช่น session ค้างจากเวอร์ชันก่อน) จะนำเข้ามิเตอร์ตามปกติ
    แต่ข้ามการบันทึกเลขอ่านและแจ้งใน logs
    """
    logs = []
    stats = {'meter_ok': 0, 'meter_reused': 0, 'reading_ok': 0, 'skipped': 0, 'errors': 0}
    result_rows = []

    save_readings = bool(billing_month and billing_year_be)
    if not save_readings and any(
        r.get('reading_before') is not None or r.get('reading_after') is not None for r in rows
    ):
        logs.append(('skip', "ไม่บันทึกเลขอ่านมิเตอร์ -- ไม่พบรอบบิล (เดือน/ปี) ที่เป็นตัวเลขใน session "
                             "กรุณาอัปโหลดไฟล์ใหม่อีกครั้ง"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for r in rows:
            row_result = dict(r)

            if r['status'] == 'skip':
                logs.append(('skip', f"SKIP  SubArea={r['subarea_id']} สัญญา {r['contract_code'] or '-'} -- {r['message']}"))
                stats['skipped'] += 1
                row_result['final_status'] = 'skip'
                result_rows.append(row_result)
                continue

            if r['status'] == 'error':
                logs.append(('err', f"ERROR  SubArea={r['subarea_id']} -- {r['message']}"))
                stats['errors'] += 1
                row_result['final_status'] = 'error'
                result_rows.append(row_result)
                continue

            # ไม่มี try/except ต่อแถวแล้ว (ตั้งใจ) -- เดิมกลืน error ของแถวแล้วไปต่อ แล้ว commit
            # ตอนจบ ผลคือแถวที่ sp_meter_save ผ่านแต่ bind/เลขอ่านล้ม ถูก commit ไปครึ่งเดียว
            # ทั้งที่หน้าจอบอกว่า error และถ้า SP ข้างใน ROLLBACK เอง งานของแถวก่อนหน้าที่ขึ้นว่า
            # สำเร็จจะหายไปเงียบๆ -- ตอนนี้ error ใดๆ ใน DB = rollback ทั้งไฟล์ แล้วแจ้งแถวที่ล้ม
            # (staged ยังอยู่ใน session ผู้ใช้แก้แล้วกดยืนยันใหม่ได้)
            try:
                # หา Meter_id เดิมก่อน -- ถ้าเจอจะส่งเข้า SP ให้เข้า branch UPDATE
                # (ใช้ cursor ตัวเดียวกับที่กำลัง commit อยู่ ให้เห็นแถวที่เพิ่ง insert ในรอบนี้ด้วย)
                existing = find_existing_meter(
                    cursor, r['subarea_id'], r['type_cd'], r['meter_no'],
                )
                reuse_id = existing[0] if existing else None

                # สำคัญ: branch UPDATE ของ SP สั่ง SET Meter_no = @Meter_no ตรงๆ และ auto-gen
                # เลขน้ำ (W001...) ทำงานแค่ใน branch INSERT เท่านั้น ถ้าแถวนี้ไม่มีเลขเครื่องวัด
                # (รอ Gen เลข) แล้วเราส่ง NULL เข้า UPDATE เลขที่ระบบ gen ไว้เดิมจะถูกล้างหาย
                # จึงต้องส่งเลข/สถานะเดิมของแถวนั้นกลับเข้าไปเพื่อรักษาค่าไว้
                if existing and not r['meter_no']:
                    meter_no_to_save, status_to_save = existing[1], existing[2]
                else:
                    meter_no_to_save, status_to_save = r['meter_no'], r['meter_no_status']

                meter_id = sp_meter_save(
                    cursor, r['location_id'], r['area_id'], r['subarea_id'], r['type_cd'],
                    meter_no_to_save, status_to_save, user_id, logs, r.get('phase_type'),
                    meter_id=reuse_id,
                )
                if not meter_id:
                    # SP ไม่คืน Meter_id ตอน INSERT -> bind/เลขอ่านจะถูกข้ามเงียบๆ ถือว่าผิดปกติ
                    raise RuntimeError('sp_Contract_Meter_Save ไม่คืน Meter_id')

                if r.get('db_contract_id'):
                    sp_bind_to_contract(
                        cursor, r['db_contract_id'], r['location_id'], r['area_id'],
                        r['subarea_id'], meter_id, user_id, logs,
                    )

                # เลขอ่านก่อน-หลังของรอบบิลที่เลือกตอนอัปโหลด -- ใช้ cursor เดิม (transaction เดียวกัน)
                # ค่าจาก session เป็น int อยู่แล้ว (parser กรองมาแล้ว) แต่ int() ซ้ำกันไว้เผื่อ
                # session ค้างจากเวอร์ชันที่ยังเก็บเป็น float ที่ไม่มีทศนิยม
                rb, ra = r.get('reading_before'), r.get('reading_after')
                if save_readings and meter_id and (rb is not None or ra is not None):
                    reading_id = sp_meter_reading_save(
                        cursor, meter_id, billing_year_be, billing_month,
                        int(rb) if rb is not None else None,
                        int(ra) if ra is not None else None,
                        user_id,
                        contract_id=r.get('db_contract_id'),
                        contract_code=r.get('contract_code'),
                    )
                    if not reading_id:
                        raise RuntimeError('sp_Contract_Meter_Reading_Save ไม่คืน Reading_id')
                    stats['reading_ok'] += 1
                    row_result['reading_saved'] = True
                    cls = 'water' if r['type_cd'] == 9 else 'electric'
                    logs.append((cls, f"EXEC sp_Contract_Meter_Reading_Save  @Meter_id={meter_id}, "
                                      f"{billing_month}/{billing_year_be}, ก่อน={rb}, หลัง={ra}  "
                                      f"-> Reading_id={reading_id}"))
            except Exception as exc:
                raise ImportRowError(r.get('idx'), r.get('subarea_id'), r.get('type_label')) from exc

            # นับสำเร็จหลังทุกขั้นของแถวผ่านแล้วเท่านั้น -- เดิมนับก่อน bind/เลขอ่าน
            # แถวที่ล้มทีหลังจึงถูกนับทั้ง meter_ok และ errors
            stats['meter_ok'] += 1
            if reuse_id:
                stats['meter_reused'] += 1
            row_result['meter_id'] = meter_id
            row_result['reused'] = bool(reuse_id)
            row_result['final_status'] = 'success'
            result_rows.append(row_result)

        # เขียน log เหตุการณ์นำเข้าไฟล์ -- ใช้ cursor เดิม จึงอยู่ในทรานแซกชันเดียวกับ
        # การนำเข้า ถ้า commit ไม่ผ่าน log ก็ไม่เกิด ไม่เหลือ log ของงานที่ไม่ได้เกิดขึ้น

        contract_ids = {r.get('db_contract_id') for r in rows if r.get('db_contract_id')}
        detail = (
            f"นำเข้าไฟล์ Excel -- บันทึกมิเตอร์ {stats['meter_ok']} รายการ "
            f"(ใช้ทะเบียนเดิม {stats['meter_reused']}) · เลขอ่าน {stats['reading_ok']} รายการ · "
            f"ข้าม {stats['skipped']} · "
            f"ผิดพลาด {stats['errors']} · สัญญาที่เกี่ยวข้อง {len(contract_ids)} ฉบับ"
        )
        if billing_period:
            detail += f" · รอบบิล {billing_period}"

        add_activity_log(
            ACTION_UPLOAD_COMMIT, user_id,
            # ผูกกับสัญญาได้เฉพาะเมื่อไฟล์นั้นเกี่ยวกับสัญญาเดียว -- ถ้าหลายสัญญา
            # ปล่อยว่างไว้ แล้วบอกจำนวนใน Detail (log 1 แถวต่อ 1 ครั้งที่นำเข้า)
            contract_id=next(iter(contract_ids)) if len(contract_ids) == 1 else None,
            ref_text=source_filename,
            detail=detail,
            cursor=cursor,
        )

        conn.commit()
    except Exception:
        # error ที่หลุดออกมานอก try ของแต่ละแถว (เช่นตอน commit เอง) -- rollback ให้ชัดเจน
        # ไม่ปล่อยให้ไปพึ่งพฤติกรรม implicit rollback ตอน conn.close()
        # ครอบ rollback อีกชั้น: ถ้า connection หลุดไปแล้ว rollback เองจะ throw
        # แล้วกลบ exception ตัวจริง (เช่น ImportRowError ที่บอกว่าแถวไหนล้ม)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    return {'logs': logs, 'stats': stats, 'rows': result_rows}
