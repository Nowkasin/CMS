# meters/signals.py
"""บันทึกการเข้า/ออกระบบลง Contract_activity_log (middleware ข้าม login/logout อยู่แล้ว)"""
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.dispatch import receiver

from .services import activity_log as activity


def _ip(request):
    return (request.META.get('REMOTE_ADDR') if request is not None else None) or '-'


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    activity.log_activity_safe(
        activity.ACTION_LOGIN, user.get_username(), ref_text=user.get_username(),
        detail=f'เข้าสู่ระบบ · IP {_ip(request)}',
    )


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is None:
        return
    activity.log_activity_safe(
        activity.ACTION_LOGOUT, user.get_username(), ref_text=user.get_username(),
        detail=f'ออกจากระบบ · IP {_ip(request)}',
    )


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    name = (credentials or {}).get('username') or '(ไม่ระบุ)'
    activity.log_activity_safe(
        activity.ACTION_LOGIN_FAILED, str(name)[:50], ref_text=str(name),
        detail=f'เข้าสู่ระบบไม่สำเร็จ · IP {_ip(request)}',
    )