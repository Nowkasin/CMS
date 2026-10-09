# meters/views/activity_log.py
"""
หน้า log เหตุการณ์รวมของระบบ -- ใครทำอะไรเมื่อไหร่

ทำเป็นหน้าเดียวรวมทุกเหตุการณ์ ไม่แยก log ต่อเมนู เพราะ:
  - คำถามที่คนถามจริงมักข้ามเมนู ("สัญญานี้มีอะไรเกิดขึ้นบ้าง")
  - มุมมองต่อเมนูทำได้ฟรีด้วย query string (?action=...) ไม่ต้องสร้างหน้าใหม่
  - เพิ่มประเภทเหตุการณ์ใหม่ไม่ต้องแตะหน้าจอ แค่เพิ่มใน ACTIVITY_ACTIONS
"""
import datetime

from django.core.paginator import Paginator
from django.shortcuts import render

from .. import services
from .dashboard import THAI_MONTHS

DEFAULT_USER = 'web_upload'
LOG_PER_PAGE = 30


def _thai_datetime(value):
    """วันเวลา -> '6 ตุลาคม 2569 16:23' (พ.ศ. เหมือนที่อื่นในระบบ)"""
    if not value:
        return None
    try:
        return (f'{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543} '
                f'{value.hour:02d}:{value.minute:02d}')
    except (AttributeError, IndexError, TypeError):
        return None


def activity_log(request):
    """
    รายการเหตุการณ์ทั้งระบบ -- กรองตามประเภท ค้นหา และแบ่งหน้า ทุกอย่างเป็น GET

    ?action=  ประเภทเหตุการณ์ (ดู services.ACTIVITY_ACTIONS) หรือ 'all'
    ?q=       รหัสสัญญา / ชื่อลูกค้า / ผู้ทำรายการ / ข้อความอ้างอิง
    ?contract= กรองเฉพาะสัญญาเดียว (ลิงก์ "ดูประวัติ" จากหน้ารายละเอียดสัญญาส่งมา)
    """
    action = request.GET.get('action', 'all')
    valid_actions = dict(services.ACTIVITY_ACTIONS)
    if action not in valid_actions:
        action = 'all'

    search = request.GET.get('q', '').strip()

    # ?contract= รับเฉพาะตัวเลข -- ค่าอื่นถือว่าไม่ได้กรอง (ไม่ throw)
    contract_raw = request.GET.get('contract', '').strip()
    contract_id = None
    if contract_raw:
        try:
            contract_id = int(contract_raw)
        except ValueError:
            contract_id = None

    rows = services.fetch_activity_log(search, action)
    if contract_id is not None:
        rows = [r for r in rows if r.get('Contract_id') == contract_id]

    # จำนวนบนแท็บนับจากทั้งตาราง (ไม่ขึ้นกับตัวกรองที่เลือกอยู่) เพื่อให้เห็นว่า
    # ประเภทอื่นมีข้อมูลรออยู่เท่าไหร่ -- ต่างจากหน้ารายการสัญญาที่นับหลังกรอง
    # เพราะที่นั่นแท็บเป็นการแบ่งกลุ่มของชุดเดียวกัน ส่วนที่นี่เป็นประเภทคนละเรื่อง
    by_action = services.count_activity_by_action()
    actions = [{'key': 'all', 'label': 'ทุกเหตุการณ์',
                'count': sum(by_action.values()), 'is_active': action == 'all'}]
    for key, label in services.ACTIVITY_ACTIONS:
        actions.append({'key': key, 'label': label,
                        'count': by_action.get(key, 0), 'is_active': action == key})

    for r in rows:
        r['at_label'] = _thai_datetime(r.get('DateEntry'))
        r['action_label'] = services.ACTION_LABELS.get(r['Action_type'], r['Action_type'])

    paginator = Paginator(rows, LOG_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'rows': page_obj.object_list,
        'total_visible': len(rows),
        'actions': actions,
        'active_action': action,
        'search': search,
        'contract_filter': contract_id,
        'default_user': DEFAULT_USER,
        # ประเภทที่ยังไม่ได้เขียน log -- บอกผู้ใช้ตรงๆ ว่าหน้านี้ยังไม่ครอบคลุมอะไร
        'pending_sources': [
            'แก้ไขมิเตอร์และบันทึกเลขอ่านจากหน้าแดชบอร์ด',
            'เพิ่ม/แก้มิเตอร์จากหน้าจัดการมิเตอร์',
            'แก้ Master ระบบไฟฟ้า',
        ],
    }
    return render(request, 'meters/activity_log.html', context)
