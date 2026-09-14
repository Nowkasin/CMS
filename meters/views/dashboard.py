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


def _safe_save_reading(meter_id, year_be, month, before_val, after_val, label, errors):
    print(f"[DEBUG] calling save_meter_reading: meter_id={meter_id!r} ({type(meter_id)}) "
          f"before_val={before_val!r} ({type(before_val)}) after_val={after_val!r} ({type(after_val)})")
    try:
        rows_updated = services.save_meter_reading(meter_id, year_be, month, before_val, after_val, DEFAULT_USER)
    except Exception as exc:
        print(f"[DEBUG] exception type={type(exc)} repr={exc!r}")
        errors.append(f"บันทึกเลขอ่าน{label}ไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบ: {exc}")
        return False

    if rows_updated == 0:
        errors.append(f"ไม่พบข้อมูลงวดค่า{label}ของเดือน {month}/{year_be} ในระบบ Installment -- บันทึกไม่สำเร็จ")
        return False

    return True


def edit_meter(request, subarea_id):
    """
    หน้าแก้ไขมิเตอร์น้ำ/ไฟของ SubArea หนึ่งๆ จาก dashboard -- เป็นการ update ข้อมูลจริงใน DB
    ทันทีที่กดบันทึก (ต่างจาก edit_staged_row ที่แก้แค่ข้อมูลใน session ก่อน commit)

    เลขอ่านก่อน-หลังอ่าน/เขียนที่ Contract_Installment_tr_dt -- save_meter_reading() ทำได้แค่
    UPDATE แถวที่มีอยู่แล้วเท่านั้น ป้องกัน error 2 ชั้น:
      1) _safe_int() ที่ view นี้ ดักค่าที่ไม่ใช่ตัวเลขก่อนแปลง
      2) _safe_save_reading() ครอบ try/except รอบการเรียก service อีกที กันทุก error หลุดเป็น 500
    """
    data = services.fetch_subarea_meters(subarea_id)
    if not data:
        return redirect('dashboard')

    year_only_errors = []
    year_raw = request.GET.get('year') or request.POST.get('billing_year')
    month_raw = request.GET.get('month') or request.POST.get('billing_month')
    year_be = _safe_int(year_raw, 'ปี', year_only_errors) or _current_year_be()
    month = _safe_int(month_raw, 'เดือน', year_only_errors) or datetime.date.today().month
    reading_errors = []

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
            print(f"[DEBUG] water before_raw={before_raw!r} after_raw={after_raw!r}")
            if before_raw or after_raw:
                errors_before_this = len(reading_errors)
                before_val = _safe_int(before_raw, 'เลขอ่านก่อน (น้ำ)', reading_errors)
                after_val = _safe_int(after_raw, 'เลขอ่านหลัง (น้ำ)', reading_errors)
                if len(reading_errors) == errors_before_this:
                    _safe_save_reading(result_meter_ids['water'], year_be, month, before_val, after_val, 'น้ำ', reading_errors)

        if electric_enabled and result_meter_ids['electric']:
            before_raw = request.POST.get('electric_reading_before', '').strip()
            after_raw = request.POST.get('electric_reading_after', '').strip()
            if before_raw or after_raw:
                errors_before_this = len(reading_errors)
                before_val = _safe_int(before_raw, 'เลขอ่านก่อน (ไฟ)', reading_errors)
                after_val = _safe_int(after_raw, 'เลขอ่านหลัง (ไฟ)', reading_errors)
                if len(reading_errors) == errors_before_this:
                    _safe_save_reading(result_meter_ids['electric'], year_be, month, before_val, after_val, 'ไฟ', reading_errors)

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
        'reading_errors': reading_errors,
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