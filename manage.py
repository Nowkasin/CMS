#!/usr/bin/env python
import os
import sys

DEFAULT_RUNSERVER_PORT = '8080'


def _inject_default_port(argv):
    """
    ถ้าสั่ง `manage.py runserver` โดยไม่ได้ระบุ port/address ต่อท้าย ให้เติม port จาก .env
    (ตัวแปร RUNSERVER_PORT, ไม่ตั้งไว้ใช้ DEFAULT_RUNSERVER_PORT) เข้าไปให้เอง
    -- Django ปกติจะใช้ 8000 ตายตัวและไม่มีไฟล์ setting ให้แก้ จึงต้องดักที่นี่

    ถ้าผู้ใช้พิมพ์ port มาเองอยู่แล้ว (เช่น `runserver 9000` หรือ `runserver 0.0.0.0:9000`)
    จะไม่ยุ่งเลย ให้ค่าที่พิมพ์มาชนะเสมอ ส่วน option ที่ขึ้นต้นด้วย '-'
    (เช่น --noreload, --insecure) ไม่นับเป็น port
    """
    if len(argv) < 2 or argv[1] != 'runserver':
        return argv

    if any(not arg.startswith('-') for arg in argv[2:]):
        return argv

    try:
        from decouple import config
        port = config('RUNSERVER_PORT', default=DEFAULT_RUNSERVER_PORT)
    except Exception:
        port = DEFAULT_RUNSERVER_PORT

    return argv + [str(port)]


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "ไม่สามารถ import Django ได้ ตรวจสอบว่าติดตั้งแล้วหรือยัง (pip install -r requirements.txt)"
        ) from exc
    execute_from_command_line(_inject_default_port(sys.argv))


if __name__ == '__main__':
    main()
