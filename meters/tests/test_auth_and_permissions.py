import time
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import resolve

from meters import permission_middleware
from meters.permissions import ACCESS_CHECKED_AT_KEY
from meters.views import auth as auth_views

from .helpers import LOCMEM_CACHE, NoDbTestCase

HOST = {'HTTP_HOST': 'localhost'}


def access(permissions):
    return {
        'person_id': 'P1', 'display_name': 'Tester', 'groups': [{'id': 'g', 'name': 'G'}],
        'has_cms_access': True, 'menus': [], 'menu_ids': [], 'permissions': permissions,
    }


@override_settings(
    CACHES=LOCMEM_CACHE,
    AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'],
)
class LoginThrottleTests(NoDbTestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        # signals เขียน login_failed ลง SQL Server -- ห้ามแตะ DB จริงใน test
        p1 = mock.patch('meters.signals.activity.log_activity_safe')
        p2 = mock.patch('django.contrib.auth.backends.ModelBackend.authenticate', return_value=None)
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def post_login(self, username='bob', ip='10.0.0.1'):
        req = self.rf.post('/login/', {'username': username, 'password': 'x'},
                           REMOTE_ADDR=ip, **HOST)
        req.user = AnonymousUser()
        req.session = SessionStore()
        return auth_views.login_view(req)

    def test_blocks_after_repeated_failures_per_user(self):
        codes = [self.post_login().status_code for _ in range(7)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5:], [429, 429])

    def test_blocked_request_does_not_try_ldap(self):
        for _ in range(5):
            self.post_login()
        with mock.patch('meters.views.auth.AuthenticationForm.is_valid') as is_valid:
            self.assertEqual(self.post_login().status_code, 429)
        is_valid.assert_not_called()

    def test_other_user_from_same_ip_not_blocked_by_user_limit(self):
        for _ in range(5):
            self.post_login('bob')
        self.assertEqual(self.post_login('alice').status_code, 200)


class SafeNextUrlTests(NoDbTestCase):
    def make(self, next_url, permissions):
        req = RequestFactory().post('/login/', {'next': next_url}, **HOST)
        req.session = {'cms_permissions': permissions}
        return auth_views._safe_next_url(req)

    def test_keeps_query_string(self):
        self.assertEqual(self.make('/download/?month=5', {'excel_download': True}),
                         '/download/?month=5')

    def test_rejects_url_without_permission(self):
        self.assertEqual(self.make('/download/', {'meter_management': True}), '/meters/')

    def test_rejects_other_host(self):
        self.assertEqual(self.make('https://evil.example/meters/', {'meter_management': True}),
                         '/meters/')


@override_settings(CMS_ACCESS_REFRESH_SECONDS=600)
class PermissionMiddlewareTests(NoDbTestCase):
    def setUp(self):
        self.mw = permission_middleware.CMSMenuPermissionMiddleware(lambda r: HttpResponse())

    def request(self, path, permissions, checked_at=None):
        req = RequestFactory().get(path, **HOST)
        req.user = User(username='bob')
        req.session = SessionStore()
        req.session['cms_permissions'] = permissions
        req.session[ACCESS_CHECKED_AT_KEY] = int(time.time()) if checked_at is None else checked_at
        req.resolver_match = resolve(path)
        return req

    def test_allowed_menu_passes(self):
        req = self.request('/meters/', {'meter_management': True})
        self.assertIsNone(self.mw.process_view(req, None, (), {}))

    def test_menu_without_permission_is_404(self):
        req = self.request('/dashboard/', {'meter_management': True})
        self.assertEqual(self.mw.process_view(req, None, (), {}).status_code, 404)

    def test_no_permission_at_all_redirects(self):
        req = self.request('/dashboard/', {})
        resp = self.mw.process_view(req, None, (), {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/no-permission/')

    def test_stale_permissions_are_refreshed_from_k2(self):
        req = self.request('/dashboard/', {'meter_management': True}, checked_at=1)
        with mock.patch.object(permission_middleware, 'fetch_user_access',
                               return_value=access({'dashboard_view': True})):
            self.assertIsNone(self.mw.process_view(req, None, (), {}))
        self.assertEqual(req.session['cms_permissions'], {'dashboard_view': True})

    def test_revoked_user_is_logged_out(self):
        req = self.request('/meters/', {'meter_management': True}, checked_at=1)
        revoked = access({})
        revoked['groups'] = []
        with mock.patch.object(permission_middleware, 'fetch_user_access', return_value=revoked), \
                mock.patch.object(permission_middleware, 'logout') as logout:
            resp = self.mw.process_view(req, None, (), {})
        logout.assert_called_once()
        self.assertEqual(resp.url, '/login/')

    def test_db_error_keeps_existing_permissions(self):
        req = self.request('/meters/', {'meter_management': True}, checked_at=1)
        with mock.patch.object(permission_middleware, 'fetch_user_access',
                               side_effect=RuntimeError('db down')):
            self.assertIsNone(self.mw.process_view(req, None, (), {}))
        self.assertGreater(req.session[ACCESS_CHECKED_AT_KEY], 1)

    def test_fresh_session_does_not_query_k2(self):
        req = self.request('/meters/', {'meter_management': True})
        with mock.patch.object(permission_middleware, 'fetch_user_access') as fetch:
            self.mw.process_view(req, None, (), {})
        fetch.assert_not_called()
