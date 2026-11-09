from django.shortcuts import redirect

from ..permissions import first_allowed_url_name


def home(request):
    """ส่งผู้ใช้ไปยังเมนูแรกที่ได้รับสิทธิ์แทนการสร้างหน้าแรกซ้ำกับ Sidebar"""
    permissions = request.session.get('cms_permissions', {})
    url_name = first_allowed_url_name(permissions)
    return redirect(url_name or 'no_permission')

