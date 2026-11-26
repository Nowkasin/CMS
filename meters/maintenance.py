"""
โหมดปรับปรุงระบบ -- ทุกหน้าตอบหน้า 503 "ปิดปรับปรุงระบบชั่วคราว"

เปิดได้ 2 ทาง (ทางใดทางหนึ่งก็พอ):
  1) ไฟล์ธง  -- python manage.py maintenance on [--message "..."] [--until "..."]
               สร้างไฟล์ CMS_MAINTENANCE_FLAG_FILE (ค่าเริ่มต้น var/maintenance.json)
               เปิด/ปิดได้ทันทีโดยไม่ต้อง restart เว็บ -- ปิดด้วย `maintenance off`
  2) .env    -- CMS_MAINTENANCE_MODE=True (ต้อง restart เว็บให้ค่ามีผล)

middleware นี้วางไว้ก่อน Session/Auth ใน settings.MIDDLEWARE โดยตั้งใจ: ระหว่างปรับปรุง
ฐานข้อมูล (SQLite/SQL Server) อาจใช้งานไม่ได้ หน้านี้จึงต้องแสดงได้โดยไม่แตะฐานข้อมูลใดๆ

ผู้ดูแลยังใช้เว็บได้ตามปกติระหว่างปรับปรุง (เพื่อตรวจหน้าตาหลังแก้ไข) 3 ทาง:
  - ลิงก์ผ่าน  -- คำสั่ง `maintenance on` สร้างรหัสสุ่มใหม่ทุกครั้งและพิมพ์ลิงก์
                  ...?maintenance_bypass=<รหัส> ให้ เปิดลิงก์ครั้งเดียว ระบบฝาก cookie ไว้
                  ในเบราว์เซอร์นั้น แล้วใช้ได้ทุกหน้าจนกว่าจะปิด/เปิดโหมดใหม่ (รหัสเปลี่ยน
                  = cookie เก่าใช้ไม่ได้) ไม่ขึ้นกับ IP จึงใช้ได้แม้อยู่หลัง IIS/proxy
  - เครื่องเซิร์ฟเวอร์เอง -- เปิดจาก localhost (127.0.0.1 / ::1) ผ่านได้เสมอ
  - IP ใน CMS_MAINTENANCE_ALLOW_IPS
ระหว่างผ่าน หน้าเว็บจะมีแถบสีส้มเตือนว่าระบบยังปิดปรับปรุงสำหรับผู้ใช้ทั่วไป
(request.cms_maintenance_bypass = True -- base.html / login.html ใช้แสดงแถบนี้)
ไฟล์ static ผ่านเสมอ (หน้า 503 ต้องใช้ฟอนต์/รูป)
"""
import json
import logging
import secrets
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 500
BYPASS_PARAM = 'maintenance_bypass'
BYPASS_COOKIE = 'cms_maintenance_bypass'
LOCALHOST_IPS = frozenset({'127.0.0.1', '::1'})


def flag_file_path():
    return Path(settings.CMS_MAINTENANCE_FLAG_FILE)


def new_bypass_token():
    return secrets.token_urlsafe(24)


def read_flag_file():
    """
    คืนข้อมูลในไฟล์ธง {'message', 'until', 'bypass_token'} หรือ None ถ้าไม่มีไฟล์ (= ไม่ได้ปิดปรับปรุง)
    ไฟล์ว่าง/อ่านไม่ออกยังถือว่าเปิดโหมดปรับปรุงอยู่ -- การมีไฟล์คือสัญญาณหลัก
    """
    path = flag_file_path()
    try:
        raw = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning('Cannot read maintenance flag file path=%s', path)
        return {}
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def maintenance_state():
    """คืนข้อมูลโหมดปรับปรุงเมื่อเปิดอยู่ ไม่งั้นคืน None"""
    flag = read_flag_file()
    if flag is None and not settings.CMS_MAINTENANCE_MODE:
        return None
    flag = flag or {}
    message = str(flag.get('message') or settings.CMS_MAINTENANCE_MESSAGE or '').strip()
    until = str(flag.get('until') or settings.CMS_MAINTENANCE_UNTIL or '').strip()
    token = str(flag.get('bypass_token') or settings.CMS_MAINTENANCE_BYPASS_TOKEN or '').strip()
    return {
        'message': message[:MAX_MESSAGE_LEN],
        'until': until[:100],
        'bypass_token': token,
    }


def bypass_url(token):
    """
    ลิงก์ผ่านไปหน้าแรกของระบบ -- ใช้ origin แรกใน DJANGO_CSRF_TRUSTED_ORIGINS เป็นที่อยู่เว็บ
    (ปกติตั้งเป็นที่อยู่จริงของ Production อยู่แล้ว) ถ้าไม่ได้ตั้งไว้คืนแค่ path ให้ผู้ใช้เติมเอง
    """
    origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', None) or ['']
    origin = origins[0].rstrip('/')
    return f'{origin}{settings.SCRIPT_NAME_PREFIX}/?{urlencode({BYPASS_PARAM: token})}'


def _client_ip(request):
    return request.META.get('REMOTE_ADDR') or ''


def _token_matches(candidate, token):
    return bool(candidate and token) and secrets.compare_digest(str(candidate), token)


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.allow_ips = frozenset(settings.CMS_MAINTENANCE_ALLOW_IPS) | LOCALHOST_IPS

    def __call__(self, request):
        state = maintenance_state()
        if state is None or request.path.startswith(settings.STATIC_URL):
            return self.get_response(request)

        token = state['bypass_token']

        # เปิดลิงก์ผ่าน: ฝาก cookie แล้ว redirect ไป URL เดิมที่ไม่มีรหัสใน address bar
        # (กันรหัสติดไปกับประวัติเบราว์เซอร์/ภาพหน้าจอ/การแชร์ลิงก์)
        if _token_matches(request.GET.get(BYPASS_PARAM), token):
            params = request.GET.copy()
            params.pop(BYPASS_PARAM, None)
            query = params.urlencode()
            response = HttpResponseRedirect(request.path + (f'?{query}' if query else ''))
            response.set_cookie(
                BYPASS_COOKIE, token,
                max_age=7 * 24 * 3600,
                path=settings.SESSION_COOKIE_PATH,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=True,
                samesite='Lax',
            )
            logger.info('Maintenance bypass granted ip=%s', _client_ip(request))
            return response

        if (_token_matches(request.COOKIES.get(BYPASS_COOKIE), token)
                or _client_ip(request) in self.allow_ips):
            request.cms_maintenance_bypass = True
            return self.get_response(request)

        response = render(request, 'meters/503.html', state, status=503)
        # บอก client/โปรแกรมตรวจสถานะว่าควรลองใหม่เมื่อไหร่ และห้าม cache หน้านี้ไว้
        # (ไม่งั้นหลังเปิดระบบแล้ว เบราว์เซอร์/proxy อาจยังแสดงหน้าปรับปรุงค้าง)
        response['Retry-After'] = str(settings.CMS_MAINTENANCE_RETRY_AFTER)
        response['Cache-Control'] = 'no-store'
        return response
