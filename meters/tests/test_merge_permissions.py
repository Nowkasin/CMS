from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from meters.context_processors import cms_ui, cms_environment
from meters.permission_middleware import CMSMenuPermissionMiddleware


@override_settings(CMS_ADMIN_GROUP_IDS=['ADMIN'])
class MergedPermissionTests(SimpleTestCase):
    def request(self, permissions, groups, method='get'):
        request = getattr(RequestFactory(), method)('/settings/')
        request.user = MagicMock(is_authenticated=True)
        request.session = {'cms_permissions': permissions, 'cms_groups': groups}
        request.resolver_match = SimpleNamespace(url_name='system_settings')
        return request

    def test_group_badge_does_not_grant_settings_permission(self):
        request = self.request({}, [{'id': 'ADMIN'}])
        self.assertTrue(cms_environment(request)['cms_is_admin'])
        self.assertFalse(cms_ui(request)['cms_can_manage_settings'])
        middleware = CMSMenuPermissionMiddleware(lambda request: None)
        with patch.object(middleware, '_refresh_access', return_value=True):
            self.assertEqual(middleware.process_view(request, None, (), {}).status_code, 404)

    def test_settings_requires_both_group_and_menu(self):
        middleware = CMSMenuPermissionMiddleware(lambda request: None)
        with patch.object(middleware, '_refresh_access', return_value=True):
            for groups, expected in (([], False), ([{'id': 'admin'}], True)):
                request = self.request({'system_settings': True}, groups)
                self.assertEqual(cms_ui(request)['cms_can_manage_settings'], expected)
                result = middleware.process_view(request, None, (), {})
                self.assertIsNone(result) if expected else self.assertEqual(result.status_code, 404)

    def test_simulated_group_cannot_change_period_settings(self):
        request = self.request({'system_settings': True}, [{'id': 'ADMIN'}], 'post')
        request.session['cms_view_as'] = {'id': 'staff'}
        middleware = CMSMenuPermissionMiddleware(lambda request: None)
        with patch.object(middleware, '_refresh_access', return_value=True):
            self.assertEqual(middleware.process_view(request, None, (), {}).status_code, 403)

    def test_maintenance_request_without_authentication_is_supported(self):
        self.assertFalse(cms_ui(RequestFactory().get('/'))['cms_can_manage_settings'])
