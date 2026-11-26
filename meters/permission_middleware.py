"""บังคับใช้สิทธิ์เมนู K2 ฝั่ง Server สำหรับทุก View ของ CMS"""

import logging
import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect, render

from .permissions import (
    ACCESS_CHECKED_AT_KEY,
    ADMIN_URL_NAMES,
    HOME_URL_NAMES,
    PUBLIC_URL_NAMES,
    URL_PERMISSION_MAP,
    VIEW_AS_ALLOWED_POST,
    VIEW_AS_KEY,
    is_cms_admin,
    reapply_view_as,
    store_access_in_session,
)
from .services.access import fetch_user_access


logger = logging.getLogger(__name__)


class CMSMenuPermissionMiddleware:
    """ป้องกันการเข้า View ที่ไม่มีสิทธิ์ แม้ผู้ใช้พิมพ์ URL โดยตรง"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def _refresh_access(request):
        """
        ดึงสิทธิ์จาก K2 ใหม่ทุก CMS_ACCESS_REFRESH_SECONDS (ค่าเริ่มต้น 10 นาที)

        เดิมสิทธิ์ถูกจำไว้ใน session ตอนล็อกอินอย่างเดียว ถ้าผู้ดูแลถอนสิทธิ์เมนูใน K2
        ผู้ใช้ที่ล็อกอินค้างอยู่ยังใช้เมนูนั้นต่อได้จนกว่า session จะหมดอายุ (2 ชั่วโมง)

        คืน False เมื่อควรบังคับออกจากระบบ (ไม่พบบุคลากร หรือไม่มีกลุ่ม CMS ที่เปิดใช้งานแล้ว
        -- เงื่อนไขเดียวกับที่ auth_backend ใช้ปฏิเสธการล็อกอิน)
        ถ้าอ่านฐานข้อมูลไม่ได้ ใช้สิทธิ์เดิมต่อไปก่อน (ไม่เตะผู้ใช้ออกเพราะ DB สะดุดชั่วคราว)
        """
        interval = getattr(settings, 'CMS_ACCESS_REFRESH_SECONDS', 600)
        checked_at = request.session.get(ACCESS_CHECKED_AT_KEY) or 0
        now = int(time.time())
        if interval <= 0 or now - checked_at < interval:
            return True

        username = request.user.get_username()
        try:
            access = fetch_user_access(username)
        except Exception as exc:
            logger.warning(
                'CMS access refresh failed user=%s error_type=%s', username, type(exc).__name__,
            )
            # เลื่อนรอบถัดไป ไม่ยิง DB ซ้ำทุก request ระหว่างที่ DB มีปัญหา
            request.session[ACCESS_CHECKED_AT_KEY] = now
            return True

        if access is None or not access['groups']:
            logger.warning('CMS access revoked, logging out user=%s', username)
            return False

        if access['permissions'] != request.session.get('cms_permissions'):
            logger.info('CMS permissions changed user=%s', username)
        store_access_in_session(request.session, access)
        # ผู้ดูแลที่กำลัง "ดูในมุมมองกลุ่ม" -- ไม่ให้สิทธิ์จริงทับสิทธิ์จำลองกลางคัน
        reapply_view_as(request.session)
        return True

    def process_view(self, request, view_func, view_args, view_kwargs):
        url_name = request.resolver_match.url_name
        if url_name in PUBLIC_URL_NAMES or not request.user.is_authenticated:
            return None

        if not self._refresh_access(request):
            # ถูกถอนกลุ่ม CMS ทั้งหมด / ไม่พบในข้อมูลบุคลากรแล้ว -> ออกจากระบบทันที
            logout(request)
            return redirect('login')

        if url_name in ADMIN_URL_NAMES:
            # ตรวจจากกลุ่มจริง ไม่ใช่สิทธิ์เมนู -- คนที่ไม่ใช่ผู้ดูแลเห็นเป็น 404 ไม่รู้ว่ามีหน้านี้
            if is_cms_admin(request.session):
                return None
            return render(request, 'meters/404.html', status=404)

        if request.session.get(VIEW_AS_KEY) and request.method not in ('GET', 'HEAD', 'OPTIONS')                 and url_name not in VIEW_AS_ALLOWED_POST:
            # โหมดดูในมุมมองกลุ่มเป็นแบบอ่านอย่างเดียว -- ปฏิเสธทุกการบันทึก/แก้ไข
            logger.info('CMS view-as blocked write user=%s url_name=%s',
                        request.user.get_username(), url_name)
            return render(request, 'meters/view_as_readonly.html', status=403)

        permissions = request.session.get('cms_permissions', {})
        if url_name in HOME_URL_NAMES:
            if permissions:
                return None
            return redirect('no_permission')

        required_permission = URL_PERMISSION_MAP.get(url_name)
        if required_permission is None:
            logger.error(
                'CMS URL has no permission mapping url_name=%s path=%s',
                url_name,
                request.path,
            )
            return render(
                request,
                'meters/404.html',
                status=404,
            )

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
            'meters/404.html',
            status=404,
        )
