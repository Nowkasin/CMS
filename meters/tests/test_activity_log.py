import datetime
import importlib
from unittest import mock

from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import resolve

from meters import log_middleware
from meters.services import activity_log

from .helpers import NoDbTestCase, fake_connection

activity_log_view = importlib.import_module('meters.views.activity_log')
HOST = {'HTTP_HOST': 'localhost'}


class LogWhereTests(NoDbTestCase):
    def test_all_filters_go_to_sql(self):
        where, params = activity_log._log_where(
            search='5%', action='login', contract_id=3, user='bob',
            date_from=datetime.date(2026, 1, 1), date_to=datetime.date(2026, 1, 31),
        )
        self.assertIn('g.Contract_id = ?', where)
        self.assertIn('g.UserEntry = ?', where)
        self.assertIn('%5[%]%', params)
        # date_to รวมทั้งวัน -> เทียบ < วันถัดไป
        self.assertEqual(params[-1], datetime.date(2026, 2, 1))

    def test_fetch_uses_sql_paging(self):
        conn, cursor = fake_connection(lambda sql, params: [])
        cursor.description = [('Log_id',)]
        with mock.patch.object(activity_log, 'get_db_connection', return_value=conn):
            activity_log.fetch_activity_log(offset=60, limit=30, action='login')
        sql, params = cursor.executed[0]
        self.assertIn('OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', sql)
        self.assertEqual(params[-2:], (60, 30))


class ActivityLogViewTests(NoDbTestCase):
    def test_page_fetches_only_requested_slice(self):
        calls = []

        def fake_fetch(offset=0, limit=None, **filters):
            calls.append((offset, limit, filters))
            return [{
                'Log_id': i, 'Action_type': 'login', 'Contract_id': None, 'Meter_id': None,
                'SubArea_id': None, 'Ref_text': '', 'Detail': '', 'UserEntry': 'bob',
                'DateEntry': datetime.datetime(2026, 1, 1, 10), 'Contract_code': None,
                'CompanyName': None, 'action_url': None, 'action_text': None,
            } for i in range(limit)]

        req = RequestFactory().get('/log/?page=4&user=bob', **HOST)
        req.user = User(username='t')
        req.session = {'cms_permissions': {'activity_log_view': True}}
        with mock.patch.object(activity_log, 'fetch_log_head', return_value=(100, 0)), \
                mock.patch.object(activity_log, 'count_activity_log', return_value=95), \
                mock.patch.object(activity_log, 'fetch_activity_log', side_effect=fake_fetch), \
                mock.patch.object(activity_log, 'fetch_activity_users', return_value=['bob']):
            resp = activity_log_view.activity_log(req)
        self.assertEqual(resp.status_code, 200)
        offset, limit, filters = calls[-1]
        self.assertEqual((offset, limit), (90, 5))
        self.assertEqual(filters['user'], 'bob')


class LogMiddlewareTests(NoDbTestCase):
    def run_middleware(self, path, post, view_result, response, fetch_patches):
        req = RequestFactory().post(path, post, **HOST)
        req.user = User(username='bob')
        req.resolver_match = resolve(path)
        mw = log_middleware.ActivityLogMiddleware(lambda r: response)
        patches = [mock.patch.object(log_middleware, name, **kw) for name, kw in fetch_patches.items()]
        patches.append(mock.patch.object(log_middleware.activity, 'log_activity_safe'))
        mocks = [p.start() for p in patches]
        try:
            mw.process_view(req, None, (), req.resolver_match.kwargs)
            if view_result is not None:
                req.activity_result = view_result
            mw(req)
        finally:
            for p in patches:
                p.stop()
        return mocks[-1]

    def test_new_meter_logged_from_db_not_form(self):
        log = self.run_middleware(
            '/meters/new/', {'meter_type_cd': '8', 'meter_no': 'typed'}, {'meter_id': 42},
            HttpResponseRedirect('/meters/'),
            {'fetch_meter_by_id': {'return_value': {
                'Meter_id': 42, 'Meter_type_cd': 9, 'Meter_no': 'W001', 'SubArea_id': 'S1'}}},
        )
        args, kwargs = log.call_args
        self.assertEqual(args[0], 'meter_create')
        self.assertEqual(kwargs['ref_text'], 'W001')
        self.assertEqual(kwargs['meter_id'], 42)

    def test_failed_new_meter_not_logged(self):
        log = self.run_middleware(
            '/meters/new/', {}, None, HttpResponseRedirect('/meters/'),
            {'fetch_meter_by_id': {'return_value': None}},
        )
        log.assert_not_called()

    def test_phase_toggle_logged_by_middleware(self):
        before = {'Phase_id': 1, 'Phase_type': '1เฟส', 'Phase_desc': 'x', 'UseOrNot': 1}
        after = dict(before, UseOrNot=0)
        log = self.run_middleware(
            '/phases/1/edit/', {}, {'phase_id': 1}, HttpResponseRedirect('/phases/'),
            {'fetch_phase_type_by_id': {'side_effect': [before, after]}},
        )
        args, kwargs = log.call_args
        self.assertEqual(args[0], 'phase_toggle')
        self.assertIn('เปิดใช้งาน → ปิดใช้งาน', kwargs['detail'])

    def test_phase_unchanged_not_logged(self):
        row = {'Phase_id': 1, 'Phase_type': '1เฟส', 'Phase_desc': 'x', 'UseOrNot': 1}
        log = self.run_middleware(
            '/phases/1/edit/', {}, {'phase_id': 1}, HttpResponseRedirect('/phases/'),
            {'fetch_phase_type_by_id': {'side_effect': [row, dict(row)]}},
        )
        log.assert_not_called()
