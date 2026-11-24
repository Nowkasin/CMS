from urllib.parse import urlsplit

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from ..permissions import (
    URL_PERMISSION_MAP,
    permission_home_url as _permission_home_url,
    store_access_in_session,
)


def _safe_next_url(request):
    permissions = request.session.get('cms_permissions', {})
    if not permissions:
        return reverse('no_permission')

    next_url = request.POST.get('next') or request.GET.get('next') or ''
    is_safe_url = url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    if is_safe_url and next_url not in {'', '/'}:
        try:
            # resolve() รับเฉพาะ path -- เดิมส่ง next ที่มี ?query ติดมา (เช่น /download/?month=5)
            # แล้วหา URL ไม่เจอ ผู้ใช้ถูกพาไปหน้าแรกแทนหน้าที่ตั้งใจจะไป
            url_name = resolve(urlsplit(next_url).path).url_name
        except Resolver404:
            url_name = None
        required_permission = URL_PERMISSION_MAP.get(url_name)
        if required_permission and permissions.get(required_permission):
            return next_url
    return _permission_home_url(permissions)


# จำกัดการเดารหัสผ่าน -- ไม่มีตัวกั้น ใครก็ยิงลอง LDAP ได้ไม่จำกัด และทุกครั้งที่ล้ม
# ยังเขียน login_failed ลง Contract_activity_log ด้วย
# นับแยกทั้ง "ต่อบัญชี" และ "ต่อ IP" ใน Django cache (ค่าเริ่มต้น LocMemCache = นับต่อ process
# ถ้า Production รันหลาย worker ให้ตั้ง CACHES เป็น backend ที่แชร์กัน เช่น database/redis)
LOGIN_MAX_FAILURES_PER_USER = 5
# ต่อ IP ตั้งสูงกว่า -- ในมหาวิทยาลัยหลายเครื่องอาจออกเน็ตด้วย IP เดียวกัน (NAT/Proxy)
LOGIN_MAX_FAILURES_PER_IP = 30
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _login_throttle_keys(request, username):
    """คืน [key ต่อบัญชี, key ต่อ IP] -- ลำดับนี้ใช้คู่กับ _login_blocked"""
    ip = request.META.get('REMOTE_ADDR') or '-'
    name = (username or '').strip().lower()
    return [f'cms-login-fail:user:{name}', f'cms-login-fail:ip:{ip}']


def _login_blocked(keys):
    user_key, ip_key = keys
    return ((cache.get(user_key) or 0) >= LOGIN_MAX_FAILURES_PER_USER
            or (cache.get(ip_key) or 0) >= LOGIN_MAX_FAILURES_PER_IP)


def _record_login_failure(keys):
    for key in keys:
        # add ไม่ทับค่าที่มีอยู่ (ตั้งอายุครั้งแรก) แล้ว incr นับต่อ
        cache.add(key, 0, LOGIN_LOCKOUT_SECONDS)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, LOGIN_LOCKOUT_SECONDS)


@login_not_required
@sensitive_post_parameters('password')
def login_view(request):
    if request.user.is_authenticated:
        return redirect(
            _permission_home_url(
                request.session.get('cms_permissions', {})
            )
        )

    form = AuthenticationForm(request, data=request.POST or None)
    throttle_keys = _login_throttle_keys(request, request.POST.get('username'))
    if request.method == 'POST' and _login_blocked(throttle_keys):
        # ไม่เรียก form.is_valid() -> ไม่ส่งรหัสผ่านไปลอง LDAP ระหว่างถูกพักไว้
        return render(
            request,
            'meters/login.html',
            {
                'form': AuthenticationForm(request),
                'next': request.POST.get('next') or request.GET.get('next', ''),
                'throttle_error': (
                    'เข้าสู่ระบบไม่สำเร็จหลายครั้งเกินไป กรุณารอประมาณ '
                    f'{LOGIN_LOCKOUT_SECONDS // 60} นาทีแล้วลองใหม่'
                ),
            },
            status=429,
        )

    if request.method == 'POST' and not form.is_valid():
        _record_login_failure(throttle_keys)

    if request.method == 'POST' and form.is_valid():
        # ล้างเฉพาะตัวนับของบัญชีนี้ -- ตัวนับต่อ IP ปล่อยให้หมดอายุเอง
        cache.delete(throttle_keys[0])
        user = form.get_user()
        login(request, user)
        store_access_in_session(request.session, {
            'person_id': getattr(user, 'cms_person_id', ''),
            'display_name': getattr(user, 'cms_display_name', user.username),
            'groups': getattr(user, 'cms_groups', []),
            'has_cms_access': getattr(user, 'cms_has_access', False),
            'menus': getattr(user, 'cms_menus', []),
            'menu_ids': getattr(user, 'cms_menu_ids', []),
            'permissions': getattr(user, 'cms_permissions', {}),
        })
        return redirect(_safe_next_url(request))

    return render(
        request,
        'meters/login.html',
        {
            'form': form,
            'next': request.POST.get('next') or request.GET.get('next', ''),
        },
    )


def no_permission_view(request):
    permissions = request.session.get('cms_permissions', {})
    if permissions:
        return redirect(_permission_home_url(permissions))

    return render(
        request,
        'meters/no_permission.html',
        status=403,
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
