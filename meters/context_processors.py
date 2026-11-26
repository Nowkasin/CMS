from django.conf import settings

from .permissions import VIEW_AS_KEY, is_cms_admin


def cms_environment(request):
    """
    ค่าที่แถบบนใช้ทุกหน้า
    - cms_environment: ชื่อสภาพแวดล้อม (เช่น DEV) ว่าง = Production ไม่แสดงป้าย
    - cms_is_admin: ผู้ใช้อยู่ในกลุ่ม CMS_ADMIN_GROUP_IDS (อ่านจาก session cms_groups ที่ได้ตอนล็อกอิน)
      ใช้แสดงป้ายและทางเข้าหน้า "ดูในมุมมองกลุ่ม" เท่านั้น สิทธิ์เข้าเมนูยังตรวจจาก cms_permissions
    - cms_group_names: ชื่อกลุ่มทั้งหมดของผู้ใช้ สำหรับ tooltip
    - cms_view_as: กลุ่มที่ผู้ดูแลระบบกำลังจำลองสิทธิ์อยู่ ({'id','name',...}) หรือ None
    """
    session = getattr(request, 'session', None)
    if session is None:
        return {'cms_environment': getattr(settings, 'CMS_ENVIRONMENT', '')}
    groups = session.get('cms_groups') or []
    return {
        'cms_environment': getattr(settings, 'CMS_ENVIRONMENT', ''),
        'cms_is_admin': is_cms_admin(session),
        'cms_group_names': ', '.join(str(g.get('name') or '').strip() for g in groups if g.get('name')),
        'cms_view_as': session.get(VIEW_AS_KEY),
    }
