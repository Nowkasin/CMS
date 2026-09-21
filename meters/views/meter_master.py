# meters/views/meter_master.py
from django.shortcuts import render, redirect

from .. import services

DEFAULT_USER = 'web_upload'


def meter_list(request):
    """
    หน้ารายการมิเตอร์ทั้งหมด (ระดับ Contract_meter_ms เอง ไม่ผูกกับสัญญา) พร้อมค้นหา/กรองประเภท
    และกรองสถานะเปิด-ปิดใช้งาน (แท็บ: ใช้งานอยู่ / ปิดใช้งาน / ทั้งหมด)
    """
    type_filter = request.GET.get('type', 'all')
    search = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'active')
    if status_filter not in ('active', 'inactive', 'all'):
        status_filter = 'active'

    context = {
        'meters': services.fetch_meters(type_filter, search, status_filter),
        'active_filter': type_filter,
        'search': search,
        'status_filter': status_filter,
    }
    return render(request, 'meters/meter_list.html', context)


def meter_form(request, meter_id=None):
    """
    ฟอร์มเพิ่ม/แก้ไขมิเตอร์ตัวเดียว -- meter_id=None คือหน้าเพิ่มใหม่, มีค่าคือหน้าแก้ไข
    ต้องเลือก SubArea ที่มีอยู่แล้วในระบบเสมอ (ดึง Location_id/Area_id จาก SubArea อัตโนมัติ)
    มี checkbox เปิด/ปิดการใช้งาน (UseOrNot) -- ค่าเริ่มต้นตอนเพิ่มใหม่คือเปิดใช้งาน (ticked)
    """
    errors = []
    meter = None
    if meter_id:
        meter = services.fetch_meter_by_id(meter_id)
        if not meter:
            return redirect('meter_list')

    if request.method == 'POST':
        subarea_id = request.POST.get('subarea_id', '').strip()
        meter_type_cd = request.POST.get('meter_type_cd')
        meter_no = request.POST.get('meter_no', '').strip()
        phase_type = request.POST.get('phase_type') or None
        meter_remark = request.POST.get('meter_remark', '').strip() or None
        use_or_not = 1 if request.POST.get('use_or_not') == 'on' else 0

        if not subarea_id:
            errors.append('กรุณาเลือกพื้นที่ย่อย (SubArea)')
        if meter_type_cd not in ('8', '9'):
            errors.append('กรุณาเลือกประเภทมิเตอร์ (น้ำ/ไฟ)')

        if not errors:
            try:
                services.save_standalone_meter(
                    subarea_id, int(meter_type_cd), meter_no, phase_type, DEFAULT_USER,
                    meter_id=meter_id, meter_remark=meter_remark, use_or_not=use_or_not,
                )
                return redirect('meter_list')
            except ValueError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f'บันทึกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบ: {exc}')

    context = {
        'subareas': services.fetch_subareas(),
        'meter': meter,
        'meter_id': meter_id,
        'errors': errors,
    }
    return render(request, 'meters/meter_form.html', context)