# meters/views/phase_master.py
"""
หน้าจัดการ Master ระบบไฟฟ้า (1 เฟส / 3 เฟส) -- requirement ข้อ 3
เดิมค่าพวกนี้ hardcode เป็น <option> ในเทมเพลต แก้จากหน้าเว็บไม่ได้
"""
from django.shortcuts import render, redirect

from .. import services
from ..services import activity_log as activity


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


def _log_phase_change(user, old, saved_id, new_type, new_desc, new_use):
    """
    บันทึกประวัติหลังบันทึกระบบไฟฟ้าสำเร็จ -- old คือแถวใน DB ก่อนแก้ (None = เพิ่มใหม่)

    ใช้ log_activity_safe: ถ้าเขียน log พลาดจะไม่ทำให้หน้าขึ้นว่า "บันทึกไม่สำเร็จ"
    ทั้งที่ข้อมูลหลักถูกบันทึกไปแล้ว (error จะไปอยู่ใน logger ของเซิร์ฟเวอร์แทน)
    """
    if old is None:
        activity.log_activity_safe(
            activity.ACTION_PHASE_CREATE, user, ref_text=new_type,
            detail=f'เพิ่มระบบไฟฟ้า "{new_type}" (Phase_id {saved_id})',
        )
        return

    changes = []
    if (old.get('Phase_type') or '') != new_type:
        changes.append(f'ชื่อ "{old.get("Phase_type")}" → "{new_type}"')
    if (old.get('Phase_desc') or '') != (new_desc or ''):
        changes.append(f'คำบรรยาย "{old.get("Phase_desc") or "-"}" → "{new_desc or "-"}"')
    status_changed = bool(old.get('UseOrNot')) != bool(new_use)
    if status_changed:
        changes.append('เปิดใช้งาน' if new_use else 'ปิดใช้งาน')

    if not changes:
        return   # กดบันทึกโดยไม่ได้เปลี่ยนอะไร ไม่ต้องลง log

    only_status = status_changed and len(changes) == 1
    activity.log_activity_safe(
        activity.ACTION_PHASE_TOGGLE if only_status else activity.ACTION_PHASE_UPDATE,
        user, ref_text=new_type, detail=' · '.join(changes),
    )


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
    phase_meters = []

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
        # รายการมิเตอร์ที่ใช้ระบบไฟฟ้านี้ -- ต้องใช้ชื่อที่อยู่ใน DB ตอนนี้ (ก่อนผู้ใช้พิมพ์แก้)
        # และต้องดึงก่อนบล็อก POST เพราะถ้าบันทึกพลาด phase จะถูกเขียนทับด้วยค่าที่พิมพ์
        phase_meters = services.fetch_meters_by_phase_type(phase['Phase_type'])

    if request.method == 'POST':
        phase_type = request.POST.get('phase_type', '').strip()
        phase_desc = request.POST.get('phase_desc', '').strip()
        use_or_not = 1 if request.POST.get('use_or_not') == 'on' else 0

        try:
            saved_id = services.save_phase_type(
                phase_type, phase_desc, request.user.get_username(),
                phase_id=phase_id, use_or_not=use_or_not,
            )
            # บันทึกประวัติหลังงานหลักสำเร็จ -- phase ตรงนี้ยังเป็นแถวใน DB ก่อนแก้
            _log_phase_change(request.user.get_username(), phase, saved_id,
                              phase_type, phase_desc, use_or_not)
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
        'phase_meters': phase_meters,
        'max_len': services.MAX_PHASE_TYPE_LEN,
        'errors': errors,
    }
    return render(request, 'meters/phase_form.html', context)