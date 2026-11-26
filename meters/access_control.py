from django.conf import settings


def is_cms_admin(request):
    """ตรวจ GroupId ที่ LDAP/K2 ส่งเข้า Session ไม่ใช้ชื่อกลุ่มหรือสิทธิ์เมนูงาน"""
    if not request.user.is_authenticated:
        return False
    if not request.session.get('cms_permissions', {}).get('system_settings'):
        return False
    allowed = {str(value).lower() for value in settings.CMS_ADMIN_GROUP_IDS}
    return any(
        isinstance(group, dict) and str(group.get('id', '')).lower() in allowed
        for group in request.session.get('cms_groups', [])
    )
