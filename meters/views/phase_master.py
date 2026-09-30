# meters/views/phase_master.py
"""
หน้าจัดการ Master ระบบไฟฟ้า (1 เฟส / 3 เฟส) -- requirement ข้อ 3
เดิมค่าพวกนี้ hardcode เป็น <option> ในเทมเพลต แก้จากหน้าเว็บไม่ได้
"""
from django.shortcuts import render, redirect

from .. import services

DEFAULT_USER = 'web_upload'


def phase_list(request):
    """
    รายการระบบไฟฟ้าทั้งหมดใน master พร้อมแท็บกรองสถานะ (ใช้งานอยู่ / ปิดใช้งาน / ทั้งหมด)
    แสดงจำนวนมิเตอร์ที่ใช้แต่ละประเภทด้วย (meters_using) เพื่อให้เห็นผลกระทบก่อนแก้ไข/ปิดใช้งาน
    """
    status_filter = request.GET.get('status', 'active')
    if status_filter not in ('active', 'inactive', 'all'):
        status_filter = 'active'

    context = {
        'phases': services.fetch_phase_types(status_filter),
        'status_filter': status_filter,
    }
    return render(request, 'meters/phase_list.html', context)


def phase_form(request, phase_id=None):
    """
    ฟอร์มเพิ่ม/แก้ไขระบบไฟฟ้า -- phase_id=None คือเพิ่มใหม่, มีค่าคือแก้ไข

    ช่อง "ชื่อระบบไฟฟ้า" (Phase_type) คือค่าที่จะถูกเขียนลง Contract_meter_ms.Phase_type จริง
    ถ้าแก้ไขค่านี้ในรายการที่มีมิเตอร์ผูกอยู่ ข้อมูลเดิมในตารางมิเตอร์จะยังเป็นค่าเก่า
    (ระบบไม่ตามไปอัปเดตให้) จึงแสดงคำเตือนพร้อมจำนวนมิเตอร์ที่ใช้อยู่บนฟอร์ม
    """
    errors = []
    phase = None
    meters_using = 0

    if phase_id:
        phase = services.fetch_phase_type_by_id(phase_id)
        if not phase:
            return redirect('phase_list')
        # หาจำนวนมิเตอร์ที่ใช้ประเภทนี้ เพื่อเตือนก่อนแก้ชื่อ/ปิดใช้งาน
        meters_using = next(
            (p['meters_using'] for p in services.fetch_phase_types('all')
             if p['Phase_id'] == phase['Phase_id']),
            0,
        )

    if request.method == 'POST':
        phase_type = request.POST.get('phase_type', '').strip()
        phase_desc = request.POST.get('phase_desc', '').strip()
        use_or_not = 1 if request.POST.get('use_or_not') == 'on' else 0

        try:
            services.save_phase_type(
                phase_type, phase_desc, DEFAULT_USER,
                phase_id=phase_id, use_or_not=use_or_not,
            )
            return redirect('phase_list')
        except ValueError as exc:
            # ValueError มาจากการ validate ของ service เอง -- ข้อความปลอดภัย แสดงให้ผู้ใช้ได้
            errors.append(str(exc))
        except Exception:
            # ไม่แสดง exception ดิบ เพราะ error จาก pyodbc/SQL Server มักมีชื่อตาราง/driver ติดมา
            errors.append('บันทึกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง')

        # กรอกผิดแล้วต้องคงค่าที่ผู้ใช้พิมพ์ไว้บนฟอร์ม ไม่ใช่ย้อนกลับเป็นค่าใน DB
        phase = {
            'Phase_id': phase_id,
            'Phase_type': phase_type,
            'Phase_desc': phase_desc,
            'UseOrNot': bool(use_or_not),
            'UserEntry': (phase or {}).get('UserEntry'),
            'DateEntry': (phase or {}).get('DateEntry'),
            'UserUpdate': (phase or {}).get('UserUpdate'),
            'DateUpdate': (phase or {}).get('DateUpdate'),
        }

    context = {
        'phase': phase,
        'phase_id': phase_id,
        'meters_using': meters_using,
        'max_len': services.MAX_PHASE_TYPE_LEN,
        'errors': errors,
    }
    return render(request, 'meters/phase_form.html', context)
