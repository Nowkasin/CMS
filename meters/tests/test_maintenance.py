import io
import json
import os
import tempfile

from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from meters.maintenance import (
    BYPASS_COOKIE,
    BYPASS_PARAM,
    MaintenanceModeMiddleware,
    maintenance_state,
)

from .helpers import NoDbTestCase

HOST = {'HTTP_HOST': 'localhost'}


class MaintenanceTests(NoDbTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.flag = os.path.join(tmp.name, 'maintenance.json')
        override = override_settings(
            CMS_MAINTENANCE_FLAG_FILE=self.flag,
            CMS_MAINTENANCE_MODE=False,
            CMS_MAINTENANCE_MESSAGE='',
            CMS_MAINTENANCE_UNTIL='',
            CMS_MAINTENANCE_ALLOW_IPS=['10.0.0.9'],
        )
        override.enable()
        self.addCleanup(override.disable)
        self.view_called = False

    def call(self, path='/meters/', ip='10.0.0.1', cookies=None):
        def view(request):
            self.view_called = True
            self.bypass_flag = getattr(request, 'cms_maintenance_bypass', False)
            return HttpResponse('ok')
        req = RequestFactory().get(path, REMOTE_ADDR=ip, **HOST)
        req.COOKIES.update(cookies or {})
        return MaintenanceModeMiddleware(view)(req)

    def token(self):
        return maintenance_state()['bypass_token']

    def command(self, *args):
        out = io.StringIO()
        call_command('maintenance', *args, stdout=out)
        return out.getvalue()

    def test_off_by_default(self):
        self.assertIsNone(maintenance_state())
        self.assertEqual(self.call().status_code, 200)

    def test_on_shows_503_without_reaching_view(self):
        self.command('on', '--message', 'ปรับปรุงฐานข้อมูล', '--until', '18:00 น.')
        resp = self.call()
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(self.view_called)
        self.assertEqual(resp['Retry-After'], '3600')
        self.assertEqual(resp['Cache-Control'], 'no-store')
        body = resp.content.decode()
        self.assertIn('ปิดปรับปรุงระบบชั่วคราว', body)
        self.assertIn('ปรับปรุงฐานข้อมูล', body)
        self.assertIn('18:00 น.', body)

    def test_message_is_escaped(self):
        with open(self.flag, 'w', encoding='utf-8') as f:
            json.dump({'message': '<script>alert(1)</script>'}, f)
        body = self.call().content.decode()
        self.assertNotIn('<script>alert(1)</script>', body)

    def test_off_command_restores_access(self):
        self.command('on')
        self.command('off')
        self.assertFalse(os.path.exists(self.flag))
        self.assertEqual(self.call().status_code, 200)

    def test_env_flag_also_enables(self):
        with override_settings(CMS_MAINTENANCE_MODE=True, CMS_MAINTENANCE_MESSAGE='จาก env'):
            resp = self.call()
        self.assertEqual(resp.status_code, 503)
        self.assertIn('จาก env', resp.content.decode())

    def test_empty_or_broken_flag_file_still_enables(self):
        with open(self.flag, 'w', encoding='utf-8') as f:
            f.write('not json')
        self.assertEqual(self.call().status_code, 503)

    def test_allowed_ip_and_static_bypass(self):
        self.command('on')
        self.assertEqual(self.call(ip='10.0.0.9').status_code, 200)
        self.assertEqual(self.call(path='/static/meters/webfonts/Prompt-Bold.ttf').status_code, 200)

    def test_localhost_always_bypasses(self):
        self.command('on')
        self.assertEqual(self.call(ip='127.0.0.1').status_code, 200)
        self.assertTrue(self.bypass_flag)

    def test_bypass_link_sets_cookie_and_hides_token(self):
        self.command('on')
        token = self.token()
        resp = self.call(f'/meters/?page=2&{BYPASS_PARAM}={token}')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/meters/?page=2')
        self.assertEqual(resp.cookies[BYPASS_COOKIE].value, token)
        self.assertTrue(resp.cookies[BYPASS_COOKIE]['httponly'])

    def test_bypass_cookie_shows_real_page(self):
        self.command('on')
        resp = self.call(cookies={BYPASS_COOKIE: self.token()})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.view_called)
        self.assertTrue(self.bypass_flag)

    def test_wrong_or_old_token_still_503(self):
        self.command('on')
        old = self.token()
        self.assertEqual(self.call(f'/meters/?{BYPASS_PARAM}=wrong').status_code, 503)
        self.command('on')   # เปิดใหม่ = รหัสใหม่ cookie เก่าใช้ไม่ได้
        self.assertNotEqual(old, self.token())
        self.assertEqual(self.call(cookies={BYPASS_COOKIE: old}).status_code, 503)

    def test_on_again_keeps_message(self):
        self.command('on', '--message', 'เดิม')
        self.command('on')
        self.assertEqual(maintenance_state()['message'], 'เดิม')

    def test_command_prints_bypass_link(self):
        out = self.command('on')
        self.assertIn(f'{BYPASS_PARAM}={self.token()}', out)

    def test_status_command(self):
        self.assertIn('ตามปกติ', self.command('status'))
        self.command('on', '--message', 'abc')
        self.assertIn('abc', self.command('status'))
