# meters/views/activity_log.py
"""
หน้า log เหตุการณ์รวมของระบบ -- ใครทำอะไรเมื่อไหร่

ทำเป็นหน้าเดียวรวมทุกเหตุการณ์ ไม่แยก log ต่อเมนู เพราะ:
  - คำถามที่คนถามจริงมักข้ามเมนู ("สัญญานี้มีอะไรเกิดขึ้นบ้าง")
  - มุมมองต่อเมนูทำได้ฟรีด้วย query string ไม่ต้องสร้างหน้าใหม่
  - เพิ่มประเภทเหตุการณ์ใหม่ไม่ต้องแตะหน้าจอ แค่เพิ่มใน ACTIVITY_ACTIONS
"""
import datetime

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render

from .. import services
from ..services import activity_log as activity
from .dashboard import THAI_MONTHS

LOG_PER_PAGE = 30


def _thai_datetime(value):
    """วันเวลา -> '6 ตุลาคม 2569 16:23:05' (พ.ศ. เหมือนที่อื่นในระบบ)"""
    if not value:
        return None
    try:
        return (f'{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543} '
                f'{value.hour:02d}:{value.minute:02d}:{value.second:02d}')
    except (AttributeError, IndexError, TypeError):
        return None


def _parse_date(text):
    """'2026-10-30' -> date; ค่าว่าง/รูปแบบผิด -> None (ข้ามตัวกรองนั้นเงียบๆ ไม่ throw)"""
    try:
        return datetime.date.fromisoformat((text or '').strip())
    except ValueError:
        return None


def _row_date(row):
    value = row.get('DateEntry')
    return value.date() if hasattr(value, 'date') else None


def activity_log(request):
    """
    รายการเหตุการณ์ทั้งระบบ -- กรอง ค้นหา และแบ่งหน้า ทุกอย่างเป็น GET (ใช้ร่วมกันได้)

    ?q=         รหัสสัญญา / ชื่อลูกค้า / ผู้ทำรายการ / ข้อความอ้างอิง
    ?user=      ผู้ทำรายการ (Buasri ID)
    ?action=    ประเภทเหตุการณ์ (ดู ACTIVITY_ACTIONS)
    ?date_from= / ?date_to=  ช่วงวันที่ YYYY-MM-DD (ใส่ด้านเดียวก็ได้)
    ?contract=  เฉพาะสัญญาเดียว (ลิงก์ "ดูประวัติ" จากหน้ารายละเอียดสัญญา)
    ?poll=1&after=<Log_id>  ใช้โดย JS ของหน้านี้เช็ครายการใหม่ -- ตอบเป็น JSON
    """
    # --- polling: ตอบแค่ตัวเลข ไม่ดึงรายการ ---
    if request.GET.get('poll') == '1':
        after = request.GET.get('after', '')
        latest, new = activity.fetch_log_head(int(after) if after.isdigit() else 0)
        return JsonResponse({'latest': latest, 'new': new})

    action = request.GET.get('action', '').strip()
    if action not in dict(services.ACTIVITY_ACTIONS):
        action = ''

    search = request.GET.get('q', '').strip()
    user_filter = request.GET.get('user', '').strip()
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))

    # ?contract= รับเฉพาะตัวเลข -- ค่าอื่นถือว่าไม่ได้กรอง (ไม่ throw)
    contract_raw = request.GET.get('contract', '').strip()
    contract_id = int(contract_raw) if contract_raw.isdigit() else None

    # อ่าน Log_id ล่าสุดก่อนดึงรายการ -- ถ้ามีรายการเข้ามาระหว่างนั้น แถบ "รายการใหม่"
    # จะนับให้ (ซ้ำได้ แต่ไม่ตกหล่น)
    latest_id, _ = activity.fetch_log_head(0)

    rows = services.fetch_activity_log(search, action or 'all')
    if contract_id is not None:
        rows = [r for r in rows if r.get('Contract_id') == contract_id]

    # รายชื่อใน dropdown มาจากผลก่อนกรองผู้ใช้/วันที่ เพื่อเปลี่ยนตัวเลือกต่อเนื่องได้
    user_options = sorted({r['UserEntry'] for r in rows if r.get('UserEntry')})

    if user_filter:
        rows = [r for r in rows if r.get('UserEntry') == user_filter]
    if date_from:
        rows = [r for r in rows if (d := _row_date(r)) and d >= date_from]
    if date_to:
        rows = [r for r in rows if (d := _row_date(r)) and d <= date_to]

    for r in rows:
        r['at_label'] = _thai_datetime(r.get('DateEntry'))
        # Action_type ที่ไม่รู้จักแสดงค่าดิบ ดีกว่าซ่อนแถวนั้นไป
        r['action_label'] = services.ACTION_LABELS.get(r['Action_type'], r['Action_type'])

    paginator = Paginator(rows, LOG_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    # query string ที่คงตัวกรองไว้ทั้งหมด (ไม่รวม page/poll) -- ใช้กับลิงก์ก่อนหน้า/ถัดไปและปุ่มโหลดใหม่
    params = request.GET.copy()
    for key in ('page', 'poll', 'after'):
        params.pop(key, None)

    context = {
        'page_obj': page_obj,
        'rows': page_obj.object_list,
        'total_visible': len(rows),
        'search': search,
        'contract_filter': contract_id or '',
        'user_filter': user_filter,
        'user_options': user_options,
        'action_filter': action,
        'action_options': services.ACTIVITY_ACTIONS,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'has_filters': bool(search or user_filter or action or date_from or date_to or contract_id),
        'qs': params.urlencode(),
        'latest_id': latest_id,
    }
    return render(request, 'meters/activity_log.html', context)