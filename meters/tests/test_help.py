import importlib
import os
import re
import time

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve

from meters import permission_middleware
from meters.permissions import ACCESS_CHECKED_AT_KEY

from .helpers import NoDbTestCase

help_view = importlib.import_module('meters.views.help')
HOST = {'HTTP_HOST': 'localhost'}


def make_request(path, permissions):
    req = RequestFactory().get(path, **HOST)
    req.user = User(username='bob')
    req.session = SessionStore()
    req.session['cms_permissions'] = permissions
    req.session[ACCESS_CHECKED_AT_KEY] = int(time.time())
    req.resolver_match = resolve(path)
    return req


class HelpPageTests(NoDbTestCase):
    def test_shows_only_sections_user_can_use(self):
        req = make_request('/help/', {'excel_download': True, 'activity_log_view': True})
        body = help_view.help_page(req).content.decode()
        self.assertIn('ดาวน์โหลด Excel สำหรับตั้งหนี้', body)
        self.assertIn('ประวัติการใช้งาน', body)
        self.assertNotIn('ยกเลิกสัญญา</h2>', body)
        self.assertNotIn('งานประจำเดือน: นำเข้าค่าน้ำ-ค่าไฟ', body)   # ภาพรวมนำเข้าแสดงเฉพาะผู้มีสิทธิ์อัปโหลด

    def test_full_permissions_render_every_demo_and_tour_link(self):
        perms = {perm: True for _k, perm, *_rest in help_view.HELP_SECTIONS}
        body = help_view.help_page(make_request('/help/', perms)).content.decode()
        # prefix ของ class เคอร์เซอร์ในแต่ละภาพสาธิต (partials/help_demo.html)
        cursor_class = {'upload': 'up', 'dashboard': 'db', 'meters': 'mt', 'download': 'dl', 'termination': 'tm'}
        for key, _perm, _title, _sum, _url, demo, _steps in help_view.HELP_SECTIONS:
            self.assertIn(f'id="{key}"', body)
            if demo:
                self.assertIn(f'demo-cursor {cursor_class[demo]}-cursor', body)
        self.assertIn('/upload/?tour=1', body)

    def test_middleware_allows_any_menu_permission(self):
        mw = permission_middleware.CMSMenuPermissionMiddleware(lambda r: HttpResponse())
        self.assertIsNone(mw.process_view(make_request('/help/', {'excel_download': True}), None, (), {}))
        resp = mw.process_view(make_request('/help/', {}), None, (), {})
        self.assertEqual(resp.url, '/no-permission/')


class TourDefinitionTests(NoDbTestCase):
    """ทุก data-tour ที่ tour.js อ้างถึงต้องมีอยู่จริงใน template -- กันเปลี่ยนชื่อแล้วทัวร์ข้ามขั้นเงียบๆ"""

    def test_tour_anchors_exist_in_templates(self):
        js = open(os.path.join(settings.BASE_DIR, 'static', 'meters', 'js', 'tour.js'), encoding='utf-8').read()
        names = set(re.findall(r'\[data-tour="([\w-]+)"\]', js))
        templates_dir = os.path.join(settings.BASE_DIR, 'templates', 'meters')
        html = ''
        for root, _dirs, files in os.walk(templates_dir):
            for name in files:
                if name.endswith('.html'):
                    html += open(os.path.join(root, name), encoding='utf-8-sig').read()
        missing = sorted(n for n in names if f'data-tour="{n}"' not in html)
        self.assertEqual(missing, [])

    def test_tour_pages_are_real_url_names(self):
        js = open(os.path.join(settings.BASE_DIR, 'static', 'meters', 'js', 'tour.js'), encoding='utf-8').read()
        block = js.split('var TOURS = {', 1)[1].split('\n  };', 1)[0]
        pages = re.findall(r'^    (\w+): \[', block, re.M)
        from django.urls import reverse
        for page in pages:
            with self.subTest(page=page):
                kwargs = {'meter_id': 1} if page == 'meter_edit' else {'subarea_id': 'A1'} if page == 'edit_meter' \
                    else {'contract_id': 1} if page == 'termination_detail' else {}
                reverse(page, kwargs=kwargs)
        self.assertGreater(len(pages), 10)
