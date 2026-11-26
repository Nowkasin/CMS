from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from .permissions import URL_PERMISSION_MAP


class DashboardURLTests(SimpleTestCase):
    def test_meter_menu_resolves_to_new_path(self):
        url = reverse('dashboard')
        self.assertTrue(url.endswith('/dashboard/meters/'))
        self.assertEqual(resolve(url).url_name, 'dashboard')

    def test_old_path_redirects_and_keeps_filters(self):
        url = reverse('dashboard_legacy')
        match = resolve(url)
        response = match.func(RequestFactory().get(url + '?month=10&year=2569'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard') + '?month=10&year=2569')
        self.assertEqual(URL_PERMISSION_MAP['dashboard_legacy'], 'dashboard_view')
