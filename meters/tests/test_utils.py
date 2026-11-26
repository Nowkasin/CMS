import datetime

from meters import utils
from meters.services.sql_utils import to_sql_like_pattern

from .helpers import NoDbTestCase


class SafeIntTests(NoDbTestCase):
    def test_valid_and_empty(self):
        errors = []
        self.assertEqual(utils.safe_int('12', 'x', errors), 12)
        self.assertIsNone(utils.safe_int('', 'x', errors))
        self.assertEqual(errors, [])

    def test_not_a_number(self):
        errors = []
        self.assertIsNone(utils.safe_int('abc', 'เดือน', errors))
        self.assertEqual(len(errors), 1)

    def test_range(self):
        errors = []
        self.assertIsNone(utils.safe_int('0', 'เดือน', errors, min_value=1, max_value=12))
        self.assertIsNone(utils.safe_int('13', 'เดือน', errors, min_value=1, max_value=12))
        self.assertEqual(len(errors), 2)


class ThaiDateTests(NoDbTestCase):
    def test_thai_date(self):
        self.assertEqual(utils.thai_date(datetime.date(2026, 6, 1)), '1 มิถุนายน 2569')
        self.assertIsNone(utils.thai_date(None))

    def test_thai_datetime(self):
        value = datetime.datetime(2026, 11, 2, 14, 35, 5)
        self.assertEqual(utils.thai_datetime(value), '2 พฤศจิกายน 2569 14:35')
        self.assertEqual(utils.thai_datetime(value, seconds=True), '2 พฤศจิกายน 2569 14:35:05')

    def test_period_label(self):
        self.assertEqual(utils.period_label('202702'), 'กุมภาพันธ์ 2570')
        self.assertIsNone(utils.period_label('202713'))
        self.assertIsNone(utils.period_label('abc'))

    def test_expired_ago_label(self):
        today = datetime.date(2026, 11, 23)
        self.assertIsNone(utils.expired_ago_label(datetime.date(2027, 1, 1), today))
        self.assertEqual(utils.expired_ago_label(datetime.date(2026, 11, 1), today), 'เดือนนี้')
        self.assertEqual(utils.expired_ago_label(datetime.date(2025, 8, 1), today), '1 ปี 3 เดือน')

    def test_parse_iso_date(self):
        self.assertEqual(utils.parse_iso_date('2026-02-28'), datetime.date(2026, 2, 28))
        self.assertIsNone(utils.parse_iso_date('2026-02-31'))


class LikePatternTests(NoDbTestCase):
    def test_escapes_sql_wildcards(self):
        # ต้องใช้คู่กับ LIKE ที่ "ไม่มี" ESCAPE clause -- [%] คือ % ตัวจริง
        self.assertEqual(to_sql_like_pattern('50%'), '%50[%]%')
        self.assertEqual(to_sql_like_pattern('a_b'), '%a[_]b%')
        self.assertEqual(to_sql_like_pattern('[x'), '%[[]x%')

    def test_user_wildcards(self):
        self.assertEqual(to_sql_like_pattern('A?1*'), '%A_1%%')

    def test_no_escape_clause_in_dashboard_search(self):
        # ESCAPE '[' ทำให้ [%] กลายเป็น % ตามด้วย ] -- ค้นหาอักขระพิเศษไม่เจอ (บั๊กเดิม)
        from meters.services import meters as meter_service
        from .helpers import fake_connection
        from unittest import mock

        conn, cursor = fake_connection(lambda sql, params: [])
        cursor.description = [('SubArea_name',)]
        with mock.patch.object(meter_service, 'get_db_connection', return_value=conn):
            meter_service.fetch_subareas('50%')
        sql, params = cursor.executed[0]
        self.assertNotIn('ESCAPE', sql)
        self.assertIn('%50[%]%', params)
