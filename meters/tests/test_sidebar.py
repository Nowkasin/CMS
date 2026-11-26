from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve

from meters.templatetags.cms_text import is_one_of

from .helpers import NoDbTestCase


def render_partial(name, path, permissions):
    req = RequestFactory().get(path, HTTP_HOST='localhost')
    req.user = User(username='tester')
    req.session = SessionStore()
    req.session['cms_permissions'] = permissions
    req.resolver_match = resolve(path)
    return render_to_string(f'meters/partials/{name}.html', request=req)


class SidebarTests(NoDbTestCase):
    def test_is_one_of(self):
        self.assertTrue(is_one_of('meter_new', 'meter_list, meter_new'))
        self.assertFalse(is_one_of('meter', 'meter_list,meter_new'))
        self.assertFalse(is_one_of(None, 'meter_list'))

    def test_active_menu_has_aria_current(self):
        html = render_partial('sidebar', '/invoice/', {'invoice_print': True, 'dashboard_view': True})
        self.assertEqual(html.count('aria-current="page"'), 1)
        active = html.split('aria-current="page"')[0].rsplit('<a href=', 1)[1]
        self.assertIn('/invoice/', active)
        self.assertIn('focus-visible:ring-2', html)

    @override_settings(CMS_ENVIRONMENT='DEV')
    def test_environment_badge_on_dev(self):
        html = render_partial('top_nav', '/invoice/', {'invoice_print': True})
        self.assertIn('data-env-badge', html)
        self.assertIn('>DEV<', html)

    @override_settings(CMS_ENVIRONMENT='')
    def test_no_badge_on_production(self):
        html = render_partial('top_nav', '/invoice/', {'invoice_print': True})
        self.assertNotIn('data-env-badge', html)


ADMIN_GROUP = {'id': '9b148353-6383-40d7-b3b8-f04fc8c5a4c5', 'name': 'ผู้ดูแลระบบ ( Admin )'}
STAFF_GROUP = {'id': '31200B53-36EC-47A1-88F2-4463A597C0F9', 'name': 'ทดสอบ หน้าบ้านสร้างสัญญา'}


@override_settings(CMS_ADMIN_GROUP_IDS=['9B148353-6383-40D7-B3B8-F04FC8C5A4C5'])
class RoleBadgeTests(NoDbTestCase):
    def render_nav(self, groups):
        req = RequestFactory().get('/invoice/', HTTP_HOST='localhost')
        req.user = User(username='tester')
        req.session = SessionStore()
        req.session['cms_permissions'] = {'invoice_print': True}
        req.session['cms_groups'] = groups
        req.resolver_match = resolve('/invoice/')
        return render_to_string('meters/partials/top_nav.html', request=req)

    def test_admin_group_shows_badge(self):
        html = self.render_nav([STAFF_GROUP, ADMIN_GROUP])   # GroupId ตัวพิมพ์เล็กก็ต้องตรง
        self.assertIn('data-role-badge>', html)
        self.assertNotIn('data-role-badge-staff', html)
        self.assertIn('กลุ่มผู้ใช้: ทดสอบ หน้าบ้านสร้างสัญญา, ผู้ดูแลระบบ ( Admin )', html)

    def test_other_groups_show_staff_badge(self):
        html = self.render_nav([STAFF_GROUP])
        self.assertNotIn('data-role-badge>', html)
        self.assertIn('data-role-badge-staff>เจ้าหน้าที่<', html)

    def test_no_groups_in_session(self):
        html = self.render_nav([])
        self.assertNotIn('data-role-badge>', html)
        self.assertIn('data-role-badge-staff', html)
        self.assertNotIn('กลุ่มผู้ใช้:', html)
