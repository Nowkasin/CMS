from datetime import date
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from .services.space_dashboard import summarize_spaces, grouped_spaces, dashboard_reference_data
from .services.space_profile import SpaceProfileError
from .views.space_dashboard import space_dashboard


class SpaceDashboardTests(SimpleTestCase):
    def rows(self):
        return [
            {'SubArea_id': 'A1', 'Location_id': '100', 'Area_id': 'A', 'Status_Area': 'เช่าอยู่', 'Business_Types_BI': 'อาหาร'},
            {'SubArea_id': 'A2', 'Location_id': '100', 'Area_id': 'A', 'Status_Area': 'ว่าง'},
            {'SubArea_id': 'A3', 'Location_id': '200', 'Area_id': 'B', 'Status_Area': 'ยกเลิก'},
        ]

    def test_counts_keep_other_status_separate_and_reject_duplicate_areas(self):
        self.assertEqual(summarize_spaces(self.rows()), {
            'total': 3, 'occupied': 1, 'vacant': 1, 'other': 1, 'rate': 33.33,
        })
        self.assertIsNone(summarize_spaces([])['rate'])
        with self.assertRaises(SpaceProfileError):
            summarize_spaces([self.rows()[0], self.rows()[0]])
        with self.assertRaises(SpaceProfileError):
            summarize_spaces([{'Status_Area': 'ว่าง'}])

    def test_grouping_counts_missing_business_without_losing_rows(self):
        groups = grouped_spaces(self.rows(), ('Business_Types_BI',))
        self.assertEqual(sum(item['total'] for item in groups), 3)
        self.assertEqual(next(item['total'] for item in groups if item['label'] == 'ไม่ระบุ'), 2)
        groups = grouped_spaces(self.rows(), ('Location_id',), {('100',): 'ประสานมิตร'})
        self.assertEqual(next(item['total'] for item in groups if item['label'] == 'ประสานมิตร'), 2)

    def request(self, params=None, permissions=None):
        request = RequestFactory().get('/', params or {})
        request.session = {'cms_permissions': permissions or {}}
        request.user = MagicMock(is_authenticated=True)
        return request

    def test_permission_is_independent_and_denies_before_query(self):
        for permissions in ({}, {'dashboard_view': True}, {'space_profile_view': True}):
            with patch('meters.views.space_dashboard.get_period_navigation') as query:
                response = space_dashboard(self.request(permissions=permissions))
            self.assertEqual(response.status_code, 404)
            query.assert_not_called()

    def test_render_open_period_and_distinguish_missing_month_from_zero(self):
        day = date(2026, 11, 30)
        with patch('meters.views.space_dashboard.get_period_navigation', return_value=(day, [])), patch('meters.views.space_dashboard.load_space_period', return_value={'rows': self.rows(), 'closed': False}), patch('meters.views.space_dashboard.dashboard_reference_data', return_value=({}, {}, {10: [{'SubArea_id': 'B', 'Status_Area': 'ว่าง'}]})):
            response = space_dashboard(self.request(permissions={'space_dashboard_view': True}))
        self.assertContains(response, '33.33%')
        self.assertContains(response, '0.00%')
        self.assertContains(response, 'ยังไม่มีข้อมูล')
        self.assertContains(response, 'อยู่ระหว่างจัดทำ')
        self.assertContains(response, 'สรุปตามประเภทธุรกิจ')
        self.assertContains(response, 'ภาพรวมพื้นที่เช่า')

    def test_invalid_period_does_not_query_live_data(self):
        with patch('meters.views.space_dashboard.get_period_navigation', return_value=(date(2026, 11, 30), [])), patch('meters.views.space_dashboard.load_space_period') as load:
            response = space_dashboard(self.request({'period': 'bad'}, {'space_dashboard_view': True}))
        self.assertContains(response, 'ไม่พบรอบข้อมูลที่เลือก')
        load.assert_not_called()

    def test_database_error_is_generic_and_connection_closes(self):
        with patch('meters.views.space_dashboard.get_period_navigation', side_effect=RuntimeError('secret')):
            response = space_dashboard(self.request(permissions={'space_dashboard_view': True}))
        self.assertContains(response, 'ไม่สามารถโหลดข้อมูลสรุปได้')
        self.assertNotContains(response, 'secret')
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = RuntimeError('db failed')
        with patch('meters.services.space_dashboard.get_db_connection', return_value=conn):
            with self.assertRaises(RuntimeError):
                dashboard_reference_data(2026)
        conn.close.assert_called_once()
        conn.commit.assert_not_called()
