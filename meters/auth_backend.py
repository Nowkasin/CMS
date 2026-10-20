"""Django authentication backend สำหรับ Buasri LDAP และสิทธิ์จากระบบ K2 เดิม"""

import logging
import re
import ssl
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from ldap3 import (
    AUTO_BIND_NO_TLS,
    AUTO_BIND_TLS_BEFORE_BIND,
    Connection,
    Server,
    Tls,
)
from ldap3.core.exceptions import LDAPException
from ldap3.utils.dn import escape_rdn

from .services.access import fetch_user_access


logger = logging.getLogger(__name__)


def _ldap_server():
    """สร้าง ldap3.Server จาก ldap:// หรือ ldaps:// พร้อม timeout และ TLS validation"""
    raw_uri = settings.LDAP_SERVER_URI.strip()
    parsed = urlparse(raw_uri if '://' in raw_uri else f'ldap://{raw_uri}')
    scheme = parsed.scheme.lower()
    if scheme not in {'ldap', 'ldaps'} or not parsed.hostname:
        raise ValueError('LDAP_SERVER_URI must use ldap:// or ldaps://')

    use_ssl = scheme == 'ldaps'
    port = parsed.port or (636 if use_ssl else 389)
    tls = Tls(validate=ssl.CERT_REQUIRED if settings.LDAP_TLS_VALIDATE else ssl.CERT_NONE)
    return Server(
        parsed.hostname,
        port=port,
        use_ssl=use_ssl,
        tls=tls,
        connect_timeout=settings.LDAP_CONNECT_TIMEOUT,
    )


class BuasriLDAPBackend(ModelBackend):
    """ตรวจ LDAP แปลง Buasri ID เป็น PERSON_ID แล้วตรวจสิทธิ์ K2 เดิม

    รหัสผ่านใช้ bind กับ LDAP เท่านั้นและไม่ถูกบันทึกลงฐานข้อมูลของระบบ
    SQL Server ถูกอ่านเฉพาะ SysUserGroupAssiciate และ SysGroup โดยไม่มีการแก้ข้อมูล
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        buasri_id = (username or kwargs.get(User.USERNAME_FIELD) or '').strip().lower()
        if not buasri_id or not password:
            return None

        if not re.fullmatch(settings.LDAP_USERNAME_PATTERN, buasri_id):
            logger.warning('LDAP authentication rejected an invalid username format')
            return None

        if not settings.LDAP_SERVER_URI or not settings.LDAP_USER_DN_TEMPLATE:
            logger.error('LDAP settings are incomplete')
            return None

        connection = None
        try:
            user_dn = settings.LDAP_USER_DN_TEMPLATE.format(
                username=escape_rdn(buasri_id)
            )
            auto_bind = (
                AUTO_BIND_TLS_BEFORE_BIND
                if settings.LDAP_START_TLS
                else AUTO_BIND_NO_TLS
            )
            connection = Connection(
                _ldap_server(),
                user=user_dn,
                password=password,
                auto_bind=auto_bind,
                receive_timeout=settings.LDAP_CONNECT_TIMEOUT,
            )

            access = fetch_user_access(buasri_id)
            if access is None:
                logger.warning(
                    'LDAP user has no personnel mapping user=%s',
                    buasri_id,
                )
                return None

            if not access['groups']:
                logger.warning(
                    'LDAP user has no active CMS group user=%s person_id=%s',
                    buasri_id,
                    access['person_id'],
                )
                return None

            # auth.User และ django_session อยู่ในฐาน default ของ Django เท่านั้น
            user, created = User.objects.get_or_create(username=buasri_id)
            if created:
                user.set_unusable_password()
                user.save(update_fields=['password'])

            if not self.user_can_authenticate(user):
                return None

            # ส่งกลุ่มไปให้ login view เก็บใน session โดยไม่สร้าง/แก้กลุ่มใน SQL Server
            user.cms_person_id = access['person_id']
            user.cms_display_name = access['display_name']
            user.cms_groups = access['groups']
            logger.info('LDAP authentication succeeded for user=%s', buasri_id)
            return user
        except (LDAPException, OSError, ValueError) as exc:
            logger.warning(
                'LDAP authentication failed for user=%s error_type=%s',
                buasri_id,
                type(exc).__name__,
            )
            return None
        except Exception as exc:
            # รวมกรณี SQL Server ตรวจสิทธิ์ไม่ได้ ให้ปฏิเสธการเข้าแทนการปล่อยหน้า 500
            logger.error(
                'CMS authorization failed for user=%s error_type=%s error=%s',
                buasri_id,
                type(exc).__name__,
                exc,
            )
            return None
        finally:
            if connection is not None and connection.bound:
                connection.unbind()
