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
        meter_no = request.POST.get('meter_no', '').strip()
        meter_remark = request.POST.get('meter_remark', '').strip() or None
        use_or_not = 1 if request.POST.get('use_or_not') == 'on' else 0

        if meter_id:
            # แก้ไขมิเตอร์เดิม: ประเภทล็อกตามค่าในฐานข้อมูล ไม่รับค่าที่ POST มา
            # (ฟอร์มก็ไม่ส่งช่องนี้มาแล้ว แต่กันไว้อีกชั้นกันการดัดแปลง request)
            # สลับประเภททีหลังจะทำให้ Meter_seq ที่รันแยกตามประเภท และเลขน้ำที่ gen ไว้ (W001...)
            # ขัดกันเอง
            meter_type_cd = str(meter['Meter_type_cd'])
        else:
            meter_type_cd = request.POST.get('meter_type_cd')

        phase_type = request.POST.get('phase_type') or None
        # มิเตอร์น้ำไม่มีระบบไฟฟ้า -- ล้างค่าทิ้งเสมอ ไม่ว่าฟอร์มจะส่งอะไรมา
        if meter_type_cd == '9':
            phase_type = None

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
                # ValueError มาจากการ validate ของ service เอง -- ข้อความปลอดภัย แสดงให้ผู้ใช้ได้
                errors.append(str(exc))
            except Exception:
                # ไม่แสดงข้อความ exception ดิบ เพราะ error จาก pyodbc/SQL Server
                # มักมีชื่อตาราง/ชื่อ driver/โครงสร้างฐานข้อมูลติดมาด้วย ไม่ควรให้ผู้ใช้เห็น
                errors.append('บันทึกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง')

    context = {
        'subareas': services.fetch_subareas(),
        'meter': meter,
        'meter_id': meter_id,
        # ตัวเลือกระบบไฟฟ้าดึงจาก Master (Contract_meter_phase_ms) ไม่ hardcode ในเทมเพลตแล้ว
        # ส่งค่าปัจจุบันไปด้วย เผื่อค่านั้นถูกปิดใช้งานใน master ภายหลัง -> ยังต้องแสดงให้เห็น
        'phase_options': services.fetch_phase_options((meter or {}).get('Phase_type')),
        'errors': errors,
    }
    return render(request, 'meters/meter_form.html', context)