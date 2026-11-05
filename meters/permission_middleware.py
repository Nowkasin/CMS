"""บังคับใช้สิทธิ์เมนู K2 ฝั่ง Server สำหรับทุก View ของ CMS"""

import logging

from django.shortcuts import redirect, render

from .permissions import (
    PERMISSION_LABELS,
    PUBLIC_URL_NAMES,
    URL_PERMISSION_MAP,
)


logger = logging.getLogger(__name__)


class CMSMenuPermissionMiddleware:
    """ป้องกันการเข้า View ที่ไม่มีสิทธิ์ แม้ผู้ใช้พิมพ์ URL โดยตรง"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        url_name = request.resolver_match.url_name
        if url_name in PUBLIC_URL_NAMES or not request.user.is_authenticated:
            return None

        required_permission = URL_PERMISSION_MAP.get(url_name)
        if required_permission is None:
            logger.error(
                'CMS URL has no permission mapping url_name=%s path=%s',
                url_name,
                request.path,
            )
            return render(
                request,
                'meters/permission_denied.html',
                {'required_permission_label': 'เมนูที่ร้องขอ'},
                status=403,
            )

        permissions = request.session.get('cms_permissions', {})
        if permissions.get(required_permission):
            return None

        logger.warning(
            'CMS permission denied user=%s url_name=%s permission=%s',
            request.user.get_username(),
            url_name,
            required_permission,
        )
        if not permissions:
            return redirect('no_permission')

        return render(
            request,
            'meters/permission_denied.html',
            {
                'required_permission_label': PERMISSION_LABELS.get(
                    required_permission,
                    'เมนูที่ร้องขอ',
                ),
            },
            status=403,
        )
