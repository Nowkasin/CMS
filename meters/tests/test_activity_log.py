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


ADMIN_ID = '9B148353-6383-40D7-B3B8-F04FC8C5A4C5'


class LogScopeTests(NoDbTestCase):
    """คนที่ไม่ใช่ผู้ดูแลระบบเห็นเฉพาะเหตุการณ์ของเมนูที่กลุ่มตัวเองมีสิทธิ์"""

    def test_allowed_actions_follow_menu_permissions(self):
        allowed = activity_log.allowed_actions_for({'invoice_print': True, 'activity_log_view': True})
        self.assertEqual(allowed, [activity_log.ACTION_INVOICE_PRINT])
        self.assertEqual(activity_log.allowed_actions_for({}), [])
        # เข้า/ออกระบบ และดูในมุมมองกลุ่ม ไม่ผูกกับเมนูใด -> ผู้ดูแลเห็นคนเดียว
        everything = activity_log.allowed_actions_for(dict.fromkeys(
            set(activity_log.ACTION_PERMISSIONS.values()), True))
        for admin_only in (activity_log.ACTION_LOGIN, activity_log.ACTION_LOGIN_FAILED,
                           activity_log.ACTION_VIEW_AS_START, activity_log.ACTION_OTHER):
            self.assertNotIn(admin_only, everything)

    def test_where_limits_action_types_with_parameters(self):
        where, params = activity_log._log_where(allowed_actions=['invoice_print', 'meter_create'])
        self.assertIn('g.Action_type IN (?, ?)', where)
        self.assertEqual(params, ['invoice_print', 'meter_create'])
        self.assertIn('1 = 0', activity_log._log_where(allowed_actions=[])[0])
        self.assertNotIn('IN (', activity_log._log_where(allowed_actions=None)[0])

    def test_poll_count_is_limited_too(self):
        conn, cursor = fake_connection(lambda sql, params: (5, 1))
        with mock.patch.object(activity_log, 'get_db_connection', return_value=conn):
            activity_log.fetch_log_head(3, allowed_actions=['invoice_print'])
        sql, params = cursor.executed[0]
        self.assertIn('Action_type IN (?)', sql)
        self.assertEqual(params, (3, 'invoice_print'))

    def render(self, session, path='/log/'):
        captured = {}

        def fake_fetch(offset=0, limit=None, **filters):
            captured.update(filters)
            return [{
                'Log_id': 1, 'Action_type': 'invoice_print', 'Contract_id': 9, 'Meter_id': None,
                'SubArea_id': None, 'Ref_text': '', 'Detail': '', 'UserEntry': 'bob',
                'DateEntry': datetime.datetime(2026, 1, 1, 10), 'Contract_code': None,
                'CompanyName': None, 'action_url': '/termination/9/', 'action_text': 'ดูสัญญา ›',
            }]

        req = RequestFactory().get(path, **HOST)
        req.user = User(username='t')
        req.session = session
        with mock.patch.object(activity_log, 'fetch_log_head', return_value=(1, 0)) as head, \
                mock.patch.object(activity_log, 'count_activity_log', return_value=1), \
                mock.patch.object(activity_log, 'fetch_activity_log', side_effect=fake_fetch), \
                mock.patch.object(activity_log, 'fetch_activity_users', return_value=[]) as users:
            body = activity_log_view.activity_log(req).content.decode()
        return body, captured, head, users

    def test_group_user_sees_only_own_menus(self):
        body, filters, head, users = self.render(
            {'cms_permissions': {'invoice_print': True, 'activity_log_view': True}, 'cms_groups': []},
            path='/log/?action=login')
        self.assertEqual(filters['allowed_actions'], ['invoice_print'])
        self.assertEqual(filters['action'], 'all')          # ?action=login ไม่มีสิทธิ์ -> ไม่กรอง
        self.assertEqual(head.call_args.kwargs['allowed_actions'], ['invoice_print'])
        self.assertEqual(users.call_args.kwargs['allowed_actions'], ['invoice_print'])
        self.assertIn('เหตุการณ์ของเมนูที่คุณมีสิทธิ์ใช้งาน', body)
        self.assertNotIn('?action=login', body)              # ไม่มีแท็บเข้าสู่ระบบ
        self.assertNotIn('/termination/9/', body)            # ไม่มีสิทธิ์ยกเลิกสัญญา -> ไม่มีปุ่มลัด

    @mock.patch.object(activity_log_view, 'is_cms_admin', return_value=True)
    def test_admin_sees_everything(self, _):
        body, filters, _, _ = self.render(
            {'cms_permissions': {'activity_log_view': True}, 'cms_groups': [{'id': ADMIN_ID}]})
        self.assertIsNone(filters['allowed_actions'])
        self.assertIn('เหตุการณ์ทั้งหมดในระบบ', body)
        self.assertIn('/termination/9/', body)

    @mock.patch.object(activity_log_view, 'is_cms_admin', return_value=True)
    def test_admin_viewing_as_group_sees_group_scope(self, _):
        _, filters, _, _ = self.render({
            'cms_permissions': {'invoice_print': True, 'activity_log_view': True},
            'cms_groups': [{'id': ADMIN_ID}], 'cms_view_as': {'id': 'x', 'name': 'G', 'permissions': {}},
        })
        self.assertEqual(filters['allowed_actions'], ['invoice_print'])

    def test_poll_uses_scope(self):
        req = RequestFactory().get('/log/?poll=1&after=5', **HOST)
        req.user = User(username='t')
        req.session = {'cms_permissions': {'invoice_print': True}, 'cms_groups': []}
        with mock.patch.object(activity_log, 'fetch_log_head', return_value=(9, 2)) as head:
            activity_log_view.activity_log(req)
        head.assert_called_once_with(5, allowed_actions=['invoice_print'])


class EmptyLogPageTests(NoDbTestCase):
    def test_no_rows_does_not_query_with_fetch_zero(self):
        """แท็บที่ไม่มีเหตุการณ์ -- เดิม SQL Server error 'FETCH ... must be greater than zero' (500)"""
        req = RequestFactory().get('/log/?action=invoice_print', **HOST)
        req.user = User(username='t')
        req.session = {'cms_permissions': {'invoice_print': True}, 'cms_groups': []}
        with mock.patch.object(activity_log, 'fetch_log_head', return_value=(0, 0)), \
                mock.patch.object(activity_log, 'count_activity_log', return_value=0), \
                mock.patch.object(activity_log, 'fetch_activity_log') as fetch, \
                mock.patch.object(activity_log, 'fetch_activity_users', return_value=[]):
            resp = activity_log_view.activity_log(req)
        self.assertEqual(resp.status_code, 200)
        fetch.assert_not_called()
