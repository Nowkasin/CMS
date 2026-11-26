"""
เปิด/ปิดโหมดปรับปรุงระบบ (หน้า 503) โดยไม่ต้อง restart เว็บ

    python manage.py maintenance on --message "ปรับปรุงฐานข้อมูล" --until "23 พ.ย. 2569 18:00 น."
    python manage.py maintenance status
    python manage.py maintenance off

`on` พิมพ์ "ลิงก์ผ่าน" ให้ผู้ดูแลเปิดดูหน้าเว็บจริงระหว่างปรับปรุงได้ (ดู meters/maintenance.py)
รหัสในลิงก์สุ่มใหม่ทุกครั้งที่สั่ง `on` -- ห้ามส่งลิงก์นี้ให้ผู้ใช้ทั่วไป
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from meters.maintenance import (
    MAX_MESSAGE_LEN,
    bypass_url,
    flag_file_path,
    maintenance_state,
    new_bypass_token,
    read_flag_file,
)


class Command(BaseCommand):
    help = 'เปิด/ปิด/ดูสถานะโหมดปรับปรุงระบบ (ทุกหน้าแสดง 503)'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['on', 'off', 'status'])
        parser.add_argument('--message', default=None, help='ข้อความแจ้งผู้ใช้บนหน้า 503')
        parser.add_argument('--until', default=None, help='เวลาที่คาดว่าจะเปิดระบบ (ข้อความอิสระ)')

    def handle(self, *args, action, message, until, **options):
        path = flag_file_path()

        if action == 'on':
            current = read_flag_file() or {}
            # สั่ง on ซ้ำเพื่อแก้ข้อความ: คงค่าที่ไม่ได้ระบุไว้ แต่สุ่มรหัสลิงก์ผ่านใหม่เสมอ
            message = current.get('message', '') if message is None else message
            until = current.get('until', '') if until is None else until
            if len(message) > MAX_MESSAGE_LEN:
                raise CommandError(f'--message ยาวเกิน {MAX_MESSAGE_LEN} อักขระ')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {'message': message, 'until': until, 'bypass_token': new_bypass_token()},
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )
            self.stdout.write(self.style.WARNING(f'เปิดโหมดปรับปรุงระบบแล้ว ({path})'))
        elif action == 'off':
            path.unlink(missing_ok=True)
            self.stdout.write(self.style.SUCCESS('ปิดโหมดปรับปรุงระบบแล้ว'))
            if settings.CMS_MAINTENANCE_MODE:
                self.stdout.write(self.style.WARNING(
                    'แต่ .env ยังตั้ง CMS_MAINTENANCE_MODE=True อยู่ -- ต้องแก้ .env แล้ว restart เว็บ'
                ))

        state = maintenance_state()
        if state is None:
            self.stdout.write('สถานะ: เปิดใช้งานตามปกติ')
            return
        self.stdout.write('สถานะ: ปิดปรับปรุง (ผู้ใช้ทั่วไปเห็นหน้า 503)')
        if state['message']:
            self.stdout.write(f"ข้อความ: {state['message']}")
        if state['until']:
            self.stdout.write(f"คาดว่าจะเปิด: {state['until']}")

        self.stdout.write('')
        self.stdout.write('ผู้ดูแลยังเข้าดูหน้าเว็บจริงได้ทาง:')
        self.stdout.write('  - เปิดเว็บจาก localhost บนเครื่องเซิร์ฟเวอร์นี้')
        if state['bypass_token']:
            url = bypass_url(state['bypass_token'])
            if not url.startswith('http'):
                url = f'<ที่อยู่เว็บ>{url}'
            self.stdout.write(f'  - ลิงก์ผ่าน (เปิดครั้งเดียว ใช้ได้ทั้งเบราว์เซอร์นั้น): {url}')
        if settings.CMS_MAINTENANCE_ALLOW_IPS:
            self.stdout.write(f"  - IP: {', '.join(settings.CMS_MAINTENANCE_ALLOW_IPS)}")
