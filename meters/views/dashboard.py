# meters/views/dashboard.py
import datetime

from django.shortcuts import render, redirect
from django.urls import reverse

from .. import services

DEFAULT_USER = 'web_upload'

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


def _current_year_be():
    return datetime.date.today().year + 543


def _safe_int(raw, field_label, errors, min_value=None, max_value=None):
    """
    แปลงค่าเป็น int อย่างปลอดภัย -- ถ้าแปลงไม่ได้ (เช่น พิมพ์ตัวอักษรปนมา) จะไม่ throw
    แต่เก็บข้อความ error ไว้ใน errors list แทน แล้วคืน None ให้ผู้เรียกข้ามการบันทึกค่านั้นไป

    min_value/max_value ใช้ตรวจช่วงที่ยอมรับได้ด้วย เพราะ "แปลงเป็น int ได้" ยังไม่พอ:
      - เดือนต้องอยู่ 1-12 เท่านั้น ส่ง ?month=99 มาจะทำให้ sp_Contract_Meter_Reading_Save
        ไปชน CHECK constraint CK_Contract_meter_reading_tr_Month แล้วเด้งเป็น error
        จากฐานข้อมูลดิบๆ แทนที่จะบอกผู้ใช้ตรงๆ ว่าเดือนไม่ถูกต้อง
      - เลขอ่านมิเตอร์ติดลบไม่ได้
    """
    if raw is None or raw == '':
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors.append(f"{field_label} ต้องเป็นตัวเลขเท่านั้น (พิมพ์มาว่า '{raw}')")
        return None

    if min_value is not None and value < min_value:
        errors.append(f"{field_label} ต้องไม่น้อยกว่า {min_value} (พิมพ์มาว่า '{raw}')")
        return None
    if max_value is not None and value > max_value:
        errors.append(f"{field_label} ต้องไม่เกิน {max_value} (พิมพ์มาว่า '{raw}')")
        return None
    return value


def _safe_save_reading(meter_id, year_be, month, before_val, after_val, label, errors,
                       contract_id=None, contract_code=None):
    """
    ครอบการเรียก save_meter_reading() ด้วย try/except กันไม่ให้ error จากฐานข้อมูลหลุดเป็น 500

    save_meter_reading() เรียก sp_Contract_Meter_Reading_Save ซึ่งทำ upsert ให้เอง
    (ไม่มีแถวก็ INSERT มีแล้วก็ UPDATE) จึงไม่มีเคส "ไม่พบงวด" เหมือนเวอร์ชันเดิมที่เขียนลง
    Contract_Installment_tr_dt แล้ว UPDATE ไม่โดนแถวไหนเลย

    ค่าที่คืนกลับมาคือ Reading_id -- ถ้าเป็น None แปลว่า SP ไม่ได้คืนแถวผลลัพธ์มา ถือว่าผิดปกติ

    contract_id/contract_code ส่งต่อไปเก็บในแถวเลขอ่าน เพื่อบันทึกว่ารอบบิลนี้อยู่ใต้สัญญาไหน
    """
    try:
        reading_id = services.save_meter_reading(
            meter_id, year_be, month, before_val, after_val, DEFAULT_USER,
            contract_id=contract_id, contract_code=contract_code,
        )
    except Exception:
        errors.append(
            f"บันทึกเลขอ่าน{label}ของเดือน {month}/{year_be} ไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล"
        )
        return False

    if not reading_id:
        errors.append(f"บันทึกเลขอ่าน{label}ของเดือน {month}/{year_be} ไม่สำเร็จ -- ระบบไม่ได้เขียนข้อมูลลงฐานข้อมูล")
        return False

    return True


def _edit_meter_context(data, year_be, month, errors):
    """
    ประกอบ context ของหน้าแก้ไขมิเตอร์ -- แยกออกมาเป็นฟังก์ชันเพราะต้องใช้ 2 ที่
    (ตอนเรนเดอร์ปกติ และตอนเด้งกลับเพราะข้อมูลที่ส่งมาไม่ผ่านการตรวจ) ถ้าปล่อยให้ประกอบ
    ซ้ำสองชุด อีกวันแก้ที่เดียวแล้วลืมที่สองจะได้หน้าจอที่ context ไม่เหมือนกัน
    """
    readings = services.fetch_readings_for_meters(
        [data['water']['Meter_id'] if data['water'] else None,
         data['electric']['Meter_id'] if data['electric'] else None],
        year_be, month,
    )
    return {
        'subarea': data,
        'water_reading': readings.get(data['water']['Meter_id']) if data['water'] else None,
        'electric_reading': readings.get(data['electric']['Meter_id']) if data['electric'] else None,
        'thai_months': THAI_MONTHS,
        'billing_month': month,
        'billing_year': year_be,
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
        'reading_errors': errors,
        # ตัวเลือกระบบไฟฟ้าดึงจาก Master (Contract_meter_phase_ms) ไม่ hardcode ในเทมเพลตแล้ว
        # ส่งค่าปัจจุบันของมิเตอร์ไฟไปด้วย เผื่อค่านั้นถูกปิดใช้งานใน master ภายหลัง
        'phase_options': services.fetch_phase_options(
            (data['electric'] or {}).get('Phase_type')
        ),
    }


def edit_meter(request, subarea_id):
    """
    หน้าแก้ไขมิเตอร์น้ำ/ไฟของ SubArea หนึ่งๆ จาก dashboard -- เป็นการ update ข้อมูลจริงใน DB
    ทันทีที่กดบันทึก (ไม่มีหน้ายืนยันเพิ่ม ต่างจาก wizard นำเข้า Excel ที่ staged ไว้ใน session ก่อน)

    ทะเบียนมิเตอร์ (เลขเครื่อง/เฟส) เขียนที่ Contract_meter_ms ผ่าน sp_Contract_Meter_Save
    ส่วนเลขอ่านก่อน-หลังอ่าน/เขียนที่ Contract_meter_reading_tr โดยจับคู่ด้วย
    Meter_id + Billing_year_be (พ.ศ.) + Billing_month และเป็น upsert -- ถ้ายังไม่มีแถวของรอบบิลนั้น
    ระบบจะสร้างให้ใหม่เอง จึงบันทึกได้เสมอ ป้องกัน error 2 ชั้น:
      1) _safe_int() ที่ view นี้ ดักค่าที่ไม่ใช่ตัวเลขก่อนแปลง
      2) _safe_save_reading() ครอบ try/except รอบการเรียก service อีกที กันทุก error หลุดเป็น 500
    """
    data = services.fetch_subarea_meters(subarea_id)
    if not data:
        return redirect('dashboard')

    # error จากการแปลงปี/เดือน -- ต้องเอาไปแสดงบนหน้าจอด้วย (รวมกับ reading_errors ตอนส่ง context)
    # ไม่งั้นถ้าผู้ใช้ส่งปี/เดือนที่ไม่ใช่ตัวเลขมา ระบบจะ fallback เป็นรอบบิลปัจจุบันแบบเงียบๆ
    # ผู้ใช้จะเห็นเลขอ่านของอีกรอบบิลโดยไม่รู้ว่าค่าที่กรอกไปถูกทิ้ง
    #
    # หมายเหตุเรื่องการ fallback: ต้องเทียบ `is None` ไม่ใช่ใช้ `or` เพราะ 0 เป็นค่า falsy
    # -- ?month=0 จะถูก `or` กลืนไปเป็นเดือนปัจจุบันแบบเงียบๆ ทั้งที่ควรฟ้องว่าเดือนไม่ถูกต้อง
    period_errors = []
    year_raw = request.GET.get('year') or request.POST.get('billing_year')
    month_raw = request.GET.get('month') or request.POST.get('billing_month')
    # ช่วงปีกว้างๆ พอให้กันค่าเพี้ยน (ปีเป็น พ.ศ.) ไม่ล็อกแคบ เพราะอาจต้องย้อนดูรอบบิลเก่า
    year_be = _safe_int(year_raw, 'ปี', period_errors, min_value=2400, max_value=2700)
    if year_be is None:
        year_be = _current_year_be()
    month = _safe_int(month_raw, 'เดือน', period_errors, min_value=1, max_value=12)
    if month is None:
        month = datetime.date.today().month
    reading_errors = []

    # สัญญาที่ผูกกับพื้นที่นี้ -- เก็บลงแถวเลขอ่านด้วย ว่ารอบบิลนี้บันทึกใต้สัญญาไหน
    # หมายเหตุ: fetch_subarea_meters() ใส่ Contract_id (int) ไว้ในคีย์ 'contract_no'
    # (ดูคอมเมนต์ในฟังก์ชันนั้น -- Contract_hrd_tr ไม่มีคอลัมน์ "เลขที่สัญญา" แยก)
    reading_contract_id = data.get('contract_no')
    reading_contract_code = data.get('contract_code')

    if request.method == 'POST':
        water_enabled = request.POST.get('water_enable') == 'on'
        electric_enabled = request.POST.get('electric_enable') == 'on'
        water_meter_no = request.POST.get('water_meter_no', '').strip() or None
        electric_meter_no = request.POST.get('electric_meter_no', '').strip() or None

        # ---------- 1) ตรวจทุกอย่างให้ครบก่อน แล้วจึงเขียนฐานข้อมูล ----------
        # เดิมเรียก save_subarea_meters() ทันทีบรรทัดแรก แล้วค่อยไปตรวจเลขอ่านทีหลัง
        # ผลคือถ้าเลขอ่านผิดรูปแบบ ทะเบียนมิเตอร์ถูก commit ไปแล้วแต่หน้าจอขึ้น error
        # ผู้ใช้เข้าใจว่า "ไม่ได้บันทึกอะไรเลย" ทั้งที่ข้อมูลส่วนหนึ่งเปลี่ยนไปแล้ว

        # กันเลขมิเตอร์เดิมหายโดยไม่ตั้งใจ: ถ้ามิเตอร์ตัวนี้มีเลขอยู่แล้ว แต่ส่งช่องว่างมา
        # sp_Contract_Meter_Save จะ UPDATE Meter_no เป็น NULL + สถานะ 'รอ Gen เลข' ทับทันที
        # เลขเดิมหายถาวร กู้ไม่ได้ (Contract_meter_ms ไม่ได้เปิด temporal/CDC จึงไม่มีประวัติให้ย้อน)
        #
        # ข้อควรรู้เรื่องการ Gen เลขอัตโนมัติ (เคยเข้าใจผิดมาแล้ว): SP มี auto-gen อยู่จริง
        # แต่อยู่ใน "สาขา INSERT" และทำเฉพาะมิเตอร์น้ำ (Meter_type_cd = 9) ที่ไม่ส่งเลขมา
        # -> จะได้ W001, W002, ... ให้เอง  ส่วนสาขา UPDATE (ซึ่งหน้านี้ใช้เสมอ เพราะแก้มิเตอร์
        # ที่มีอยู่แล้ว) ทำ SET Meter_no = @Meter_no ตรงๆ ไม่มี auto-gen ใดๆ
        # ดังนั้นในหน้านี้ "เว้นว่าง" = ลบเลขทิ้ง ไม่ใช่ "ให้ระบบ gen ให้"
        for enabled, submitted, existing, label in (
            (water_enabled, water_meter_no, data['water'], 'น้ำ'),
            (electric_enabled, electric_meter_no, data['electric'], 'ไฟฟ้า'),
        ):
            if enabled and not submitted and existing and existing.get('Meter_no'):
                reading_errors.append(
                    f"เลขประจำตัวเครื่องวัด{label}ถูกเว้นว่างไว้ ทั้งที่มิเตอร์ตัวนี้มีเลข "
                    f"'{existing['Meter_no']}' อยู่แล้ว -- ถ้าต้องการเปลี่ยนเลข ให้กรอกเลขใหม่ลงไป "
                    f"ถ้าต้องการเลิกใช้มิเตอร์ตัวนี้ ให้เอาเครื่องหมายถูกหน้าหัวข้อออกแทน "
                    f"(ระบบไม่ได้ Gen เลขใหม่ให้อัตโนมัติ เว้นว่างแล้วเลขเดิมจะหายถาวร)"
                )

        # แปลง/ตรวจเลขอ่านทั้ง 4 ช่องไว้ก่อน ยังไม่เขียนลงฐานข้อมูล
        pending_readings = []
        for prefix, label in (('water', 'น้ำ'), ('electric', 'ไฟ')):
            if not (water_enabled if prefix == 'water' else electric_enabled):
                continue
            before_raw = request.POST.get(f'{prefix}_reading_before', '').strip()
            after_raw = request.POST.get(f'{prefix}_reading_after', '').strip()
            if not (before_raw or after_raw):
                continue
            errors_before_this = len(reading_errors)
            before_val = _safe_int(before_raw, f'เลขอ่านก่อน ({label})', reading_errors, min_value=0)
            after_val = _safe_int(after_raw, f'เลขอ่านหลัง ({label})', reading_errors, min_value=0)
            if len(reading_errors) == errors_before_this:
                pending_readings.append((prefix, label, before_val, after_val))

        # period_errors ต้องบล็อกการบันทึกด้วย -- ถ้าปี/เดือนที่ส่งมาไม่ถูกต้อง ระบบจะ fallback
        # ไปรอบบิลปัจจุบัน แล้วเลขอ่านจะถูกเขียนลงรอบบิลที่ผู้ใช้ไม่ได้ตั้งใจ
        if period_errors or reading_errors:
            return render(request, 'meters/edit_meter.html',
                          _edit_meter_context(data, year_be, month, period_errors + reading_errors))

        # ---------- 2) ผ่านการตรวจหมดแล้ว จึงเขียน ----------
        _logs, result_meter_ids = services.save_subarea_meters(
            location_id=data['Location_id'], area_id=data['Area_id'], subarea_id=data['SubArea_id'],
            user_id=DEFAULT_USER,
            water_enabled=water_enabled,
            water_meter_id=data['water']['Meter_id'] if data['water'] else None,
            water_meter_no=water_meter_no,
            electric_enabled=electric_enabled,
            electric_meter_id=data['electric']['Meter_id'] if data['electric'] else None,
            electric_meter_no=electric_meter_no,
            electric_phase=request.POST.get('electric_phase') or None,
        )

        for prefix, label, before_val, after_val in pending_readings:
            meter_id = result_meter_ids[prefix]
            if not meter_id:
                continue
            _safe_save_reading(
                meter_id, year_be, month, before_val, after_val, label, reading_errors,
                contract_id=reading_contract_id, contract_code=reading_contract_code,
            )

        if not reading_errors:
            return redirect(f"{reverse('edit_meter', args=[subarea_id])}?year={year_be}&month={month}")

        data = services.fetch_subarea_meters(subarea_id)

    return render(request, 'meters/edit_meter.html',
                  _edit_meter_context(data, year_be, month, period_errors + reading_errors))


def dashboard(request):
    """
    ตารางบนหน้านี้แสดง "พื้นที่ย่อย 1 แถว" (fetch_subareas) ไม่ใช่ "มิเตอร์ 1 แถว"
    เดิม view ดึง fetch_meters() มาด้วยเพื่อให้แท็บ "ทั้งหมด" เอาไปนับ ผลคือ:
      - แท็บบอก (50) ซึ่งเป็นจำนวนมิเตอร์ แต่นับแถวในตารางได้ 13 (จำนวนพื้นที่)
      - ?type=8/9 ส่งเข้า fetch_meters ตัวที่ไม่ได้เรนเดอร์ จึงไม่มีผลต่อตารางเลย
        คลิกแท็บ "มิเตอร์น้ำ" แล้วตารางยังเหมือนเดิมทุกแถว
      - แท็บน้ำ/ไฟ นับจาก stats ที่ไม่สนคำค้น ค้นหาแล้วเลขในแท็บไม่ขยับ
    ตอนนี้ตัวเลขทุกตัวในแถบแท็บมาจากชุดข้อมูลเดียวกับตาราง และกรองตามคำค้นเดียวกัน
    (นับเป็น "จำนวนพื้นที่" ให้ตรงกับจำนวนแถว ส่วนการ์ดด้านบนยังนับ "จำนวนมิเตอร์" ตามเดิม)
    """
    type_filter = request.GET.get('type', 'all')
    if type_filter not in ('all', '8', '9'):
        type_filter = 'all'
    search = request.GET.get('q', '')

    # ดึงครั้งเดียวโดยไม่กรองประเภท แล้วค่อยนับ/กรองในหน่วยความจำ -- ได้ตัวเลขทั้ง 3 แท็บ
    # ที่การันตีว่าสอดคล้องกันและตรงกับแถวที่เรนเดอร์ โดยไม่ต้องยิง query เพิ่ม 3 รอบ
    all_rows = services.fetch_subareas(search)
    tab_counts = {
        'all': len(all_rows),
        'water': sum(1 for r in all_rows if (r.get('water_meter_count') or 0) > 0),
        'electric': sum(1 for r in all_rows if (r.get('electric_meter_count') or 0) > 0),
    }
    if type_filter == '9':
        subareas = [r for r in all_rows if (r.get('water_meter_count') or 0) > 0]
    elif type_filter == '8':
        subareas = [r for r in all_rows if (r.get('electric_meter_count') or 0) > 0]
    else:
        subareas = all_rows

    context = {
        'stats': services.fetch_dashboard_stats(),
        'subareas': subareas,
        'tab_counts': tab_counts,
        'active_filter': type_filter,
        'search': search,
    }
    return render(request, 'meters/dashboard.html', context)