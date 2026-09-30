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


def _safe_int(raw, field_label, errors):
    """
    แปลงค่าเป็น int อย่างปลอดภัย -- ถ้าแปลงไม่ได้ (เช่น พิมพ์ตัวอักษรปนมา) จะไม่ throw
    แต่เก็บข้อความ error ไว้ใน errors list แทน แล้วคืน None ให้ผู้เรียกข้ามการบันทึกค่านั้นไป
    """
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        errors.append(f"{field_label} ต้องเป็นตัวเลขเท่านั้น (พิมพ์มาว่า '{raw}')")
        return None


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
    period_errors = []
    year_raw = request.GET.get('year') or request.POST.get('billing_year')
    month_raw = request.GET.get('month') or request.POST.get('billing_month')
    year_be = _safe_int(year_raw, 'ปี', period_errors) or _current_year_be()
    month = _safe_int(month_raw, 'เดือน', period_errors) or datetime.date.today().month
    reading_errors = []

    # สัญญาที่ผูกกับพื้นที่นี้ -- เก็บลงแถวเลขอ่านด้วย ว่ารอบบิลนี้บันทึกใต้สัญญาไหน
    # หมายเหตุ: fetch_subarea_meters() ใส่ Contract_id (int) ไว้ในคีย์ 'contract_no'
    # (ดูคอมเมนต์ในฟังก์ชันนั้น -- Contract_hrd_tr ไม่มีคอลัมน์ "เลขที่สัญญา" แยก)
    reading_contract_id = data.get('contract_no')
    reading_contract_code = data.get('contract_code')

    if request.method == 'POST':
        water_enabled = request.POST.get('water_enable') == 'on'
        electric_enabled = request.POST.get('electric_enable') == 'on'

        _logs, result_meter_ids = services.save_subarea_meters(
            location_id=data['Location_id'], area_id=data['Area_id'], subarea_id=data['SubArea_id'],
            user_id=DEFAULT_USER,
            water_enabled=water_enabled,
            water_meter_id=data['water']['Meter_id'] if data['water'] else None,
            water_meter_no=request.POST.get('water_meter_no', '').strip() or None,
            electric_enabled=electric_enabled,
            electric_meter_id=data['electric']['Meter_id'] if data['electric'] else None,
            electric_meter_no=request.POST.get('electric_meter_no', '').strip() or None,
            electric_phase=request.POST.get('electric_phase') or None,
        )

        if water_enabled and result_meter_ids['water']:
            before_raw = request.POST.get('water_reading_before', '').strip()
            after_raw = request.POST.get('water_reading_after', '').strip()
            if before_raw or after_raw:
                errors_before_this = len(reading_errors)
                before_val = _safe_int(before_raw, 'เลขอ่านก่อน (น้ำ)', reading_errors)
                after_val = _safe_int(after_raw, 'เลขอ่านหลัง (น้ำ)', reading_errors)
                if len(reading_errors) == errors_before_this:
                    _safe_save_reading(
                        result_meter_ids['water'], year_be, month, before_val, after_val, 'น้ำ', reading_errors,
                        contract_id=reading_contract_id, contract_code=reading_contract_code,
                    )

        if electric_enabled and result_meter_ids['electric']:
            before_raw = request.POST.get('electric_reading_before', '').strip()
            after_raw = request.POST.get('electric_reading_after', '').strip()
            if before_raw or after_raw:
                errors_before_this = len(reading_errors)
                before_val = _safe_int(before_raw, 'เลขอ่านก่อน (ไฟ)', reading_errors)
                after_val = _safe_int(after_raw, 'เลขอ่านหลัง (ไฟ)', reading_errors)
                if len(reading_errors) == errors_before_this:
                    _safe_save_reading(
                        result_meter_ids['electric'], year_be, month, before_val, after_val, 'ไฟ', reading_errors,
                        contract_id=reading_contract_id, contract_code=reading_contract_code,
                    )

        if not reading_errors:
            return redirect(f"{reverse('edit_meter', args=[subarea_id])}?year={year_be}&month={month}")

        data = services.fetch_subarea_meters(subarea_id)

    readings = services.fetch_readings_for_meters(
        [data['water']['Meter_id'] if data['water'] else None,
         data['electric']['Meter_id'] if data['electric'] else None],
        year_be, month,
    )
    water_reading = readings.get(data['water']['Meter_id']) if data['water'] else None
    electric_reading = readings.get(data['electric']['Meter_id']) if data['electric'] else None

    context = {
        'subarea': data,
        'water_reading': water_reading,
        'electric_reading': electric_reading,
        'thai_months': THAI_MONTHS,
        'billing_month': month,
        'billing_year': year_be,
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
        'reading_errors': period_errors + reading_errors,
        # ตัวเลือกระบบไฟฟ้าดึงจาก Master (Contract_meter_phase_ms) ไม่ hardcode ในเทมเพลตแล้ว
        # ส่งค่าปัจจุบันของมิเตอร์ไฟไปด้วย เผื่อค่านั้นถูกปิดใช้งานใน master ภายหลัง
        'phase_options': services.fetch_phase_options(
            (data['electric'] or {}).get('Phase_type')
        ),
    }
    return render(request, 'meters/edit_meter.html', context)


def dashboard(request):
    type_filter = request.GET.get('type', 'all')
    search = request.GET.get('q', '')
    context = {
        'stats': services.fetch_dashboard_stats(),
        'meters': services.fetch_meters(type_filter, search),
        'subareas': services.fetch_subareas(search),
        'active_filter': type_filter,
        'search': search,
    }
    return render(request, 'meters/dashboard.html', context)