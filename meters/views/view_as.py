"""
ผู้ดูแลระบบ "ดูในมุมมองกลุ่ม" -- จำลองสิทธิ์เมนูของกลุ่ม K2 อื่นเพื่อตรวจว่ากลุ่มนั้นเห็นอะไร

- เข้าได้เฉพาะผู้ดูแลระบบ (CMSMenuPermissionMiddleware ตรวจจากกลุ่มจริงผ่าน ADMIN_URL_NAMES)
- ระหว่างจำลองเป็นแบบอ่านอย่างเดียว: middleware ปฏิเสธทุก POST ยกเว้นเปลี่ยนกลุ่ม/เลิกจำลอง/ออกจากระบบ
- เริ่ม/เลิกจำลองลง activity log ผ่าน log_middleware (view ฝากชื่อกลุ่มไว้ใน request.activity_result)
- ไม่แก้ข้อมูลกลุ่ม/สิทธิ์ใน K2 -- อ่านจาก SysGroup / SysMenuGroupAssociate อย่างเดียว
"""
import logging
import re

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..permissions import PERMISSION_LABELS, PERMISSION_HOME_ROUTES, VIEW_AS_KEY, start_view_as, stop_view_as
from ..services.access import fetch_cms_groups, fetch_group_access

logger = logging.getLogger(__name__)

GUID_RE = re.compile(r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$')
MENU_ORDER = [key for key, _ in PERMISSION_HOME_ROUTES]


def _menu_labels(permissions):
    return [PERMISSION_LABELS[key] for key in MENU_ORDER if permissions.get(key)]


def view_as(request):
    """หน้าเลือกกลุ่มที่จะจำลอง"""
    error = ''
    groups = []
    try:
        groups = fetch_cms_groups()
    except Exception:
        logger.exception('view_as: อ่านรายชื่อกลุ่มไม่สำเร็จ')
        error = 'อ่านรายชื่อกลุ่มจากฐานข้อมูลไม่สำเร็จ ลองใหม่อีกครั้ง'
    for group in groups:
        group['menu_labels'] = _menu_labels(group['permissions'])
    if not error and request.GET.get('error') == '1':
        error = 'ไม่พบกลุ่มนี้ หรือกลุ่มนี้ไม่มีเมนู CMS'
    current = request.session.get(VIEW_AS_KEY)
    return render(request, 'meters/view_as.html', {
        'groups': groups,
        'error': error,
        'current_id': current['id'] if current else '',
    })


@require_POST
def view_as_start(request):
    group_id = (request.POST.get('group_id') or '').strip()
    group = None
    if GUID_RE.match(group_id):
        try:
            group = fetch_group_access(group_id)
        except Exception:
            logger.exception('view_as_start: อ่านสิทธิ์กลุ่มไม่สำเร็จ')
    if not group:
        return redirect(reverse('view_as') + '?error=1')
    start_view_as(request.session, group)
    request.activity_result = {'group_name': group['name'], 'menu_labels': _menu_labels(group['permissions'])}
    return redirect(request.session['cms_home_url'])


@require_POST
def view_as_stop(request):
    name = stop_view_as(request.session)
    if name:
        request.activity_result = {'group_name': name}
    return redirect(request.session.get('cms_home_url') or 'home')
