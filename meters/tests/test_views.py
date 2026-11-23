import glob
import importlib
import os
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.template.loader import get_template
from django.test import RequestFactory

from meters import services
from meters.services.excel_export import build_subareas_workbook

from .helpers import NoDbTestCase

dashboard_view = importlib.import_module('meters.views.dashboard')
steppage_view = importlib.import_module('meters.views.steppage')
HOST = {'HTTP_HOST': 'localhost'}


def make_request(method, path, data=None):
    req = getattr(RequestFactory(), method)(path, data or {}, **HOST)
    req.user = User(username='bob')
    req.session = SessionStore()
    return req


class TemplateCompileTests(NoDbTestCase):
    def test_all_templates_compile(self):
        root = os.path.join(settings.BASE_DIR, 'templates')
        for path in glob.glob(os.path.join(root, 'meters', '**', '*.html'), recursive=True):
            name = os.path.relpath(path, root).replace(os.sep, '/')
            with self.subTest(template=name):
                get_template(name)


class RestartTests(NoDbTestCase):
    def test_get_does_not_clear_staged_data(self):
        req = make_request('get', '/restart/')
        req.session['staged'] = {'rows': []}
        steppage_view.restart(req)
        self.assertIn('staged', req.session)

    def test_post_clears_staged_data(self):
        req = make_request('post', '/restart/')
        req.session['staged'] = {'rows': []}
        req.session['committed'] = {'rows': []}
        steppage_view.restart(req)
        self.assertNotIn('staged', req.session)
        self.assertNotIn('committed', req.session)


class StepThreeTests(NoDbTestCase):
    def test_import_row_error_shows_row_and_keeps_staged(self):
        req = make_request('post', '/confirm/', {'confirm': 'on'})
        req.session['staged'] = {'filename': 'f.xlsx', 'billing_period': 'x', 'rows': []}
        err = services.ImportRowError(7, 'S7', 'น้ำ')
        err.__cause__ = RuntimeError('raw driver text')
        with mock.patch.object(services, 'commit_staged_rows', side_effect=err):
            resp = steppage_view.step3_confirm(req)
        body = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('แถวที่ 7', body)
        self.assertNotIn('raw driver text', body)
        self.assertIn('staged', req.session)


class EditMeterTests(NoDbTestCase):
    SUBAREA = {
        'Location_id': 'L1', 'Area_id': 'A1', 'SubArea_id': 'S1', 'SubArea_name': 'n',
        'Area_name': 'a', 'Location_name': 'l', 'contract_code': None, 'contract_no': None,
        'customer_id': None, 'customer_name': None,
        'water': {'Meter_id': 1, 'Meter_type_cd': 9, 'Meter_no': 'W1', 'Phase_type': None},
        'electric': None,
    }

    def test_db_error_on_save_renders_message_instead_of_500(self):
        req = make_request('post', '/dashboard/edit/S1/', {
            'water_enable': 'on', 'water_meter_no': 'W1',
            'billing_year': '2569', 'billing_month': '11',
        })
        with mock.patch.object(services, 'fetch_subarea_meters', return_value=self.SUBAREA), \
                mock.patch.object(services, 'fetch_readings_for_meters', return_value={}), \
                mock.patch.object(services, 'fetch_phase_options', return_value=[]), \
                mock.patch.object(services, 'save_subarea_meters', side_effect=RuntimeError('db')):
            resp = dashboard_view.edit_meter(req, 'S1')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('บันทึกทะเบียนมิเตอร์ไม่สำเร็จ', resp.content.decode())


class ExportTests(NoDbTestCase):
    def test_formula_like_text_is_written_as_text(self):
        wb = build_subareas_workbook([{'customer_name': '=HYPERLINK("http://x")'}])
        self.assertEqual(wb.active['E2'].data_type, 's')
