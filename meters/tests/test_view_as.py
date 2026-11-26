"""ผู้ดูแลระบบ "ดูในมุมมองกลุ่ม" -- จำลองสิทธิ์เมนู อ่านอย่างเดียว (SQL Server mock ทั้งหมด)"""
import importlib
import time
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, override_settings
from django.urls import resolve

from meters import log_middleware, permission_middleware
from meters.permissions import (
    ACCESS_CHECKED_AT_KEY, VIEW_AS_KEY, VIEW_AS_REAL_KEY, reapply_view_as, start_view_as, stop_view_as,
)
from meters.services import access as access_service
from meters.services import activity_log as activity

from .helpers import NoDbTestCase, fake_connection

view_as_views = importlib.import_module('meters.views.view_as')

ADMIN_ID = '9B148353-6383-40D7-B3B8-F04FC8C5A4C5'
GROUP_ID = '31200B53-36EC-47A1-88F2-4463A597C0F9'
ADMIN_GROUPS = [{'id': ADMIN_ID, 'name': 'ผู้ดูแลระบบ ( Admin )'}]
STAFF_GROUPS = [{'id': GROUP_ID, 'name': 'ทดสอบ หน้าบ้านสร้างสัญญา'}]
ADMIN_PERMS = {'meter_management': True, 'invoice_print': True, 'dashboard_view': True}
FRONT_DESK = {'id': GROUP_ID, 'name': 'ทดสอบ หน้าบ้านสร้างสัญญา', 'permissions': {'invoice_print': True}}


def make_request(path, method='get', groups=ADMIN_GROUPS, permissions=None, data=None):
    req = getattr(RequestFactory(), method)(path, data or {}, HTTP_HOST='localhost')
    req.user = User(username='admin.t')
    req.session = SessionStore()
    req.session['cms_groups'] = groups
    req.session['cms_permissions'] = dict(permissions if permissions is not None else ADMIN_PERMS)
    req.session['cms_home_url'] = '/meters/'
    req.session[ACCESS_CHECKED_AT_KEY] = int(time.time())
    req.resolver_match = resolve(path)
    return req


@override_settings(CMS_ADMIN_GROUP_IDS=[ADMIN_ID])
class ViewAsSessionTests(NoDbTestCase):
    def test_start_swaps_permissions_and_stop_restores(self):
        session = make_request('/').session
        start_view_as(session, FRONT_DESK)
        self.assertEqual(session['cms_permissions'], {'invoice_print': True})
        self.assertEqual(session['cms_home_url'], '/invoice/')
        self.assertEqual(session[VIEW_AS_REAL_KEY]['permissions'], ADMIN_PERMS)

        # เปลี่ยนกลุ่มกลางทาง -- ของจริงต้องยังเป็นของผู้ดูแล ไม่ใช่ของกลุ่มก่อนหน้า
        start_view_as(session, dict(FRONT_DESK, id='X', name='อื่น', permissions={'dashboard_view': True}))
        self.assertEqual(session[VIEW_AS_REAL_KEY]['permissions'], ADMIN_PERMS)

        self.assertEqual(stop_view_as(session), 'อื่น')
        self.assertEqual(session['cms_permissions'], ADMIN_PERMS)
        self.assertEqual(session['cms_home_url'], '/meters/')
        self.assertNotIn(VIEW_AS_KEY, session)

    def test_stop_without_view_as_is_noop(self):
        session = make_request('/').session
        self.assertIsNone(stop_view_as(session))
        self.assertEqual(session['cms_permissions'], ADMIN_PERMS)

    def test_refresh_keeps_simulated_permissions(self):
        session = make_request('/').session
        start_view_as(session, FRONT_DESK)
        session['cms_permissions'] = {'meter_management': True}   # store_access_in_session เขียนของจริงทับ
        reapply_view_as(session)
        self.assertEqual(session['cms_permissions'], {'invoice_print': True})
        self.assertEqual(session[VIEW_AS_REAL_KEY]['permissions'], {'meter_management': True})

    def test_refresh_ends_view_as_when_no_longer_admin(self):
        session = make_request('/').session
        start_view_as(session, FRONT_DESK)
        session['cms_groups'] = STAFF_GROUPS
        session['cms_permissions'] = {'meter_management': True}
        reapply_view_as(session)
        self.assertNotIn(VIEW_AS_KEY, session)
        self.assertEqual(session['cms_permissions'], {'meter_management': True})


@override_settings(CMS_ADMIN_GROUP_IDS=[ADMIN_ID])
class ViewAsMiddlewareTests(NoDbTestCase):
    def setUp(self):
        self.mw = permission_middleware.CMSMenuPermissionMiddleware(lambda r: HttpResponse())

    def test_admin_page_is_404_for_non_admin(self):
        req = make_request('/admin/view-as/', groups=STAFF_GROUPS)
        self.assertEqual(self.mw.process_view(req, None, (), {}).status_code, 404)

    def test_admin_page_open_for_admin_even_while_viewing_as(self):
        req = make_request('/admin/view-as/')
        start_view_as(req.session, FRONT_DESK)
        self.assertIsNone(self.mw.process_view(req, None, (), {}))

    def test_simulated_permissions_are_enforced(self):
        req = make_request('/meters/')
        start_view_as(req.session, FRONT_DESK)
        self.assertEqual(self.mw.process_view(req, None, (), {}).status_code, 404)
        req = make_request('/invoice/')
        start_view_as(req.session, FRONT_DESK)
        self.assertIsNone(self.mw.process_view(req, None, (), {}))

    def test_writes_are_blocked_while_viewing_as(self):
        req = make_request('/meters/new/', method='post')
        start_view_as(req.session, dict(FRONT_DESK, permissions={'meter_management': True}))
        resp = self.mw.process_view(req, None, (), {})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('อ่านอย่างเดียว', resp.content.decode())

    def test_stop_and_logout_still_allowed(self):
        for path in ('/admin/view-as/stop/', '/logout/'):
            req = make_request(path, method='post')
            start_view_as(req.session, FRONT_DESK)
            self.assertIsNone(self.mw.process_view(req, None, (), {}), path)

    def test_admin_writes_normally_without_view_as(self):
        req = make_request('/meters/new/', method='post')
        self.assertIsNone(self.mw.process_view(req, None, (), {}))

    def test_periodic_refresh_does_not_undo_view_as(self):
        req = make_request('/invoice/')
        start_view_as(req.session, FRONT_DESK)
        req.session[ACCESS_CHECKED_AT_KEY] = 1
        fresh = {'person_id': 'P1', 'display_name': 'Admin', 'groups': ADMIN_GROUPS, 'has_cms_access': True,
                 'menus': [], 'menu_ids': [], 'permissions': ADMIN_PERMS}
        with mock.patch.object(permission_middleware, 'fetch_user_access', return_value=fresh):
            self.assertIsNone(self.mw.process_view(req, None, (), {}))
        self.assertEqual(req.session['cms_permissions'], {'invoice_print': True})


@override_settings(CMS_ADMIN_GROUP_IDS=[ADMIN_ID])
class ViewAsViewTests(NoDbTestCase):
    def test_picker_lists_groups_with_menu_labels(self):
        groups = [dict(FRONT_DESK, permissions={'invoice_print': True, 'meter_management': True})]
        with mock.patch.object(view_as_views, 'fetch_cms_groups', return_value=groups):
            body = view_as_views.view_as(make_request('/admin/view-as/')).content.decode()
        self.assertIn('ทดสอบ หน้าบ้านสร้างสัญญา', body)
        self.assertIn('จัดการมิเตอร์', body)
        self.assertIn('ใบแจ้งหนี้', body)
        self.assertIn(f'value="{GROUP_ID}"', body)

    def test_picker_db_error(self):
        with mock.patch.object(view_as_views, 'fetch_cms_groups', side_effect=RuntimeError('db')):
            body = view_as_views.view_as(make_request('/admin/view-as/')).content.decode()
        self.assertIn('อ่านรายชื่อกลุ่มจากฐานข้อมูลไม่สำเร็จ', body)

    def test_start_switches_and_redirects_to_group_home(self):
        req = make_request('/admin/view-as/start/', method='post', data={'group_id': GROUP_ID})
        with mock.patch.object(view_as_views, 'fetch_group_access', return_value=FRONT_DESK) as fetch:
            resp = view_as_views.view_as_start(req)
        fetch.assert_called_once_with(GROUP_ID)
        self.assertEqual(resp.url, '/invoice/')
        self.assertEqual(req.session[VIEW_AS_KEY]['name'], 'ทดสอบ หน้าบ้านสร้างสัญญา')
        self.assertEqual(req.activity_result['menu_labels'], ['ใบแจ้งหนี้'])

    def test_start_rejects_bad_id_without_query(self):
        req = make_request('/admin/view-as/start/', method='post', data={'group_id': "x'; DROP"})
        with mock.patch.object(view_as_views, 'fetch_group_access') as fetch:
            resp = view_as_views.view_as_start(req)
        fetch.assert_not_called()
        self.assertEqual(resp.url, '/admin/view-as/?error=1')
        self.assertNotIn(VIEW_AS_KEY, req.session)

    def test_start_unknown_group(self):
        req = make_request('/admin/view-as/start/', method='post', data={'group_id': GROUP_ID})
        with mock.patch.object(view_as_views, 'fetch_group_access', return_value=None):
            resp = view_as_views.view_as_start(req)
        self.assertEqual(resp.url, '/admin/view-as/?error=1')

    def test_stop_restores_and_reports_group(self):
        req = make_request('/admin/view-as/stop/', method='post')
        start_view_as(req.session, FRONT_DESK)
        resp = view_as_views.view_as_stop(req)
        self.assertEqual(resp.url, '/meters/')
        self.assertEqual(req.activity_result, {'group_name': 'ทดสอบ หน้าบ้านสร้างสัญญา'})

    def test_banner_shows_while_viewing_as(self):
        req = make_request('/admin/view-as/')
        start_view_as(req.session, FRONT_DESK)
        with mock.patch.object(view_as_views, 'fetch_cms_groups', return_value=[FRONT_DESK]):
            body = view_as_views.view_as(req).content.decode()
        self.assertIn('data-view-as-banner', body)
        self.assertIn('กำลังดูอยู่', body)


class ViewAsLogTests(NoDbTestCase):
    def test_start_and_stop_are_logged(self):
        for name, data, action in (
            ('view_as_start', {'group_name': 'G', 'menu_labels': ['ใบแจ้งหนี้']}, activity.ACTION_VIEW_AS_START),
            ('view_as_stop', {'group_name': 'G'}, activity.ACTION_VIEW_AS_STOP),
        ):
            req = make_request(f'/admin/view-as/{name.split("_")[-1]}/', method='post')
            req.activity_result = data
            result = log_middleware._view_as_build(req, {}, None, HttpResponseRedirect('/'))
            self.assertEqual(result['action'], action)
            self.assertEqual(result['ref_text'], 'G')
            if name == 'view_as_start':
                self.assertIn('เมนูของกลุ่ม: ใบแจ้งหนี้', result['detail'])

    def test_failed_start_is_not_logged(self):
        req = make_request('/admin/view-as/start/', method='post')
        self.assertIsNone(log_middleware._view_as_build(req, {}, None, HttpResponseRedirect('/')))


class GroupAccessServiceTests(NoDbTestCase):
    def test_groups_are_collected_and_sorted(self):
        rows = [
            ('31200b53-36ec-47a1-88f2-4463a597c0f9', 'หน้าบ้าน', 'invoice_print'),
            ('31200b53-36ec-47a1-88f2-4463a597c0f9', 'หน้าบ้าน', 'meter_management'),
            ('9b148353-6383-40d7-b3b8-f04fc8c5a4c5', 'Admin', 'dashboard_view'),
            ('9b148353-6383-40d7-b3b8-f04fc8c5a4c5', 'Admin', None),
        ]
        conn, cursor = fake_connection(lambda sql, params: rows)
        with mock.patch.object(access_service, 'get_db_connection', return_value=conn):
            groups = access_service.fetch_cms_groups()
        self.assertEqual([g['name'] for g in groups], ['Admin', 'หน้าบ้าน'])
        self.assertEqual(groups[1]['permissions'], {'invoice_print': True, 'meter_management': True})
        self.assertEqual(groups[1]['id'], GROUP_ID)
        self.assertEqual(cursor.executed[0][1], ('water_electric_new',))
        conn.close.assert_called_once()

    def test_group_access_uses_parameter(self):
        rows = [('31200b53-36ec-47a1-88f2-4463a597c0f9', 'หน้าบ้าน', 'invoice_print')]
        conn, cursor = fake_connection(lambda sql, params: rows)
        with mock.patch.object(access_service, 'get_db_connection', return_value=conn):
            group = access_service.fetch_group_access(GROUP_ID)
        self.assertEqual(group, {'id': GROUP_ID, 'name': 'หน้าบ้าน', 'permissions': {'invoice_print': True}})
        sql, params = cursor.executed[0]
        self.assertEqual(params, ('water_electric_new', GROUP_ID))
        self.assertNotIn(GROUP_ID, sql)

    def test_group_without_cms_menu(self):
        conn, _ = fake_connection(lambda sql, params: [])
        with mock.patch.object(access_service, 'get_db_connection', return_value=conn):
            self.assertIsNone(access_service.fetch_group_access(GROUP_ID))
