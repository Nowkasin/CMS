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
from django.urls import Resolver404, resolve

from .. import services
from ..permissions import URL_PERMISSION_MAP, VIEW_AS_KEY, is_cms_admin
from ..utils import thai_datetime
from ..services import activity_log as activity

LOG_PER_PAGE = 30


def _parse_date(text):
    """'2026-10-30' -> date; ค่าว่าง/รูปแบบผิด -> None (ข้ามตัวกรองนั้นเงียบๆ ไม่ throw)"""
    try:
        return datetime.date.fromisoformat((text or '').strip())
    except ValueError:
        return None


class _LogPage:
    """
    ลำดับแบบ lazy ให้ Paginator -- นับด้วย COUNT(*) และดึงเฉพาะหน้าที่แสดงด้วย OFFSET/FETCH
    (เดิมดึง log ทั้งตารางมาแบ่งหน้าใน Python ซึ่งช้าลงตามจำนวน log ที่เพิ่มขึ้นทุกวัน)
    """

    def __init__(self, filters):
        self.filters = filters

    def count(self):
        return activity.count_activity_log(**self.filters)

    def __getitem__(self, key):
        if not isinstance(key, slice):
            raise TypeError('_LogPage รองรับเฉพาะ slice')
        start = key.start or 0
        stop = key.stop if key.stop is not None else start
        if stop <= start:
            # ไม่มีรายการตรงตัวกรอง Paginator ขอช่วงว่าง [0:0] -- SQL Server ไม่รับ FETCH NEXT 0 ROWS
            return []
        return activity.fetch_activity_log(
            offset=start, limit=max(stop - start, 0), **self.filters
        )


def _log_scope(session):
    """
    ชนิดเหตุการณ์ที่ผู้ใช้เห็นได้ -- None = ทั้งหมด (ผู้ดูแลระบบ)
    คนอื่นเห็นเฉพาะเหตุการณ์ของเมนูที่กลุ่มตัวเองมีสิทธิ์ (activity.ACTION_PERMISSIONS)
    ผู้ดูแลที่กำลัง "ดูในมุมมองกลุ่ม" เห็นแบบกลุ่มนั้น เพื่อให้จำลองได้ตรงกับของจริง
    """
    if is_cms_admin(session) and not session.get(VIEW_AS_KEY):
        return None
    return activity.allowed_actions_for(session.get('cms_permissions'))


def _can_open(url, permissions):
    """ปุ่มลัดในแถว log พาไปหน้าที่ผู้ใช้มีสิทธิ์เท่านั้น (ไม่งั้นกดแล้วเจอ 404)"""
    try:
        required = URL_PERMISSION_MAP.get(resolve(url).url_name)
    except Resolver404:
        return False
    return bool(required and permissions.get(required))


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
    allowed = _log_scope(request.session)
    if request.GET.get('poll') == '1':
        after = request.GET.get('after', '')
        latest, new = activity.fetch_log_head(int(after) if after.isdigit() else 0, allowed_actions=allowed)
        return JsonResponse({'latest': latest, 'new': new})

    action_options = [(key, label) for key, label in services.ACTIVITY_ACTIONS
                      if allowed is None or key in allowed]
    action = request.GET.get('action', '').strip()
    if action not in dict(action_options):
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
    latest_id, _ = activity.fetch_log_head(0, allowed_actions=allowed)

    filters = {
        'search': search,
        'action': action or 'all',
        'contract_id': contract_id,
        'user': user_filter or None,
        'date_from': date_from,
        'date_to': date_to,
        'allowed_actions': allowed,
    }
    # รายชื่อใน dropdown มาจากผลก่อนกรองผู้ใช้/วันที่ เพื่อเปลี่ยนตัวเลือกต่อเนื่องได้
    user_options = activity.fetch_activity_users(
        search=search, action=action or 'all', contract_id=contract_id, allowed_actions=allowed,
    )

    permissions = request.session.get('cms_permissions') or {}
    paginator = Paginator(_LogPage(filters), LOG_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))
    rows = list(page_obj.object_list)

    for r in rows:
        r['at_label'] = thai_datetime(r.get('DateEntry'), seconds=True)
        # Action_type ที่ไม่รู้จักแสดงค่าดิบ ดีกว่าซ่อนแถวนั้นไป
        r['action_label'] = services.ACTION_LABELS.get(r['Action_type'], r['Action_type'])
        if allowed is not None and r.get('action_url') and not _can_open(r['action_url'], permissions):
            r['action_url'] = r['action_text'] = None

    # query string ที่คงตัวกรองไว้ทั้งหมด (ไม่รวม page/poll) -- ใช้กับลิงก์ก่อนหน้า/ถัดไปและปุ่มโหลดใหม่
    params = request.GET.copy()
    for key in ('page', 'poll', 'after'):
        params.pop(key, None)
    if not action:
        params.pop('action', None)   # ?action= ที่ไม่มีสิทธิ์/ไม่รู้จัก ไม่พาต่อไปลิงก์อื่น

    context = {
        'page_obj': page_obj,
        'rows': rows,
        'total_visible': paginator.count,
        'search': search,
        'contract_filter': contract_id or '',
        'user_filter': user_filter,
        'user_options': user_options,
        'action_filter': action,
        'action_options': action_options,
        'log_scoped': allowed is not None,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'has_filters': bool(search or user_filter or action or date_from or date_to or contract_id),
        'qs': params.urlencode(),
        'latest_id': latest_id,
    }
    return render(request, 'meters/activity_log.html', context)