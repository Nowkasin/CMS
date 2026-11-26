import datetime
import io
import json
from unittest import mock

from django.test import override_settings
from openpyxl import Workbook

from meters.services import excel_import

from .helpers import NoDbTestCase

HEADERS = [
    'ปีที่สร้างสัญญา', 'เลขที่สัญญา', 'รหัสสัญญา', 'Area_id', 'SubArea_id',
    'ยืนยันพื้นที่ที่คิดค่าน้ำ', 'เลขประจำเครื่องวัดน้ำ',
    'เลขที่อ่านครั้งหลัง ตย. พ.ค.69', 'เลขที่อ่านครั้งก่อน',
]


def make_workbook(rows, sheet='สัญญาปี2569_น้ำประปา', headers=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class ParseExcelTests(NoDbTestCase):
    def setUp(self):
        patches = [
            mock.patch.object(excel_import, 'find_subarea', return_value=('L1', 'A1', 'S1', 'n')),
            mock.patch.object(excel_import, 'find_contract_by_code', return_value=(99, 'C1')),
            mock.patch.object(excel_import, 'find_registered_meter', return_value=None),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def parse(self, rows, **kwargs):
        return excel_import.parse_excel_staged(make_workbook(rows, **kwargs))

    def test_rows_are_json_serializable(self):
        # เซลล์วันที่เคยหลุดลง session ตรงๆ แล้วพังตอน Django บันทึก session (หน้า 500)
        out = self.parse([[datetime.datetime(2026, 1, 5), 12, 'C1', 'A1', 'S1', 1, 'M1', 20, 10]])
        json.dumps(out['rows'])
        self.assertEqual(out['rows'][0]['contract_year'], '5/1/2569')

    def test_float_meter_number_and_text_confirm(self):
        out = self.parse([[2569, 12, ' C1 ', 'A1', 'S1', '1', 12345.0, 20, 10]])
        row = out['rows'][0]
        self.assertEqual(row['status'], 'ok')
        self.assertEqual(row['meter_no'], '12345')
        self.assertEqual(row['contract_code'], 'C1')
        self.assertEqual(row['db_contract_id'], 99)

    def test_no_meter_is_skipped(self):
        out = self.parse([[2569, 12, 'C1', 'A1', 'S1', 1, 'ไม่มีมิเตอร์', None, None]])
        self.assertEqual(out['rows'][0]['status'], 'skip')

    def test_reading_after_less_than_before_is_error(self):
        out = self.parse([[2569, 12, 'C1', 'A1', 'S1', 1, 'M1', 5, 10]])
        self.assertEqual(out['rows'][0]['status'], 'error')

    def test_duplicate_in_file_is_skipped(self):
        row = [2569, 12, 'C1', 'A1', 'S1', 1, 'M1', 20, 10]
        out = self.parse([row, row])
        self.assertEqual([r['status'] for r in out['rows']], ['ok', 'skip'])

    def test_lookups_are_cached_per_file(self):
        rows = [[2569, 12, 'C1', 'A1', 'S1', 1, f'M{i}', 20, 10] for i in range(5)]
        self.parse(rows)
        find_subarea, find_contract, _ = self.mocks
        self.assertEqual(find_subarea.call_count, 1)
        self.assertEqual(find_contract.call_count, 1)

    @override_settings(EXCEL_UPLOAD_MAX_ROWS=2)
    def test_row_limit_stops_before_more_lookups(self):
        rows = [[2569, 12, 'C1', 'A1', f'S{i}', 1, 'M1', 20, 10] for i in range(10)]
        with self.assertRaisesMessage(ValueError, 'เกิน'):
            self.parse(rows)
        self.assertLessEqual(self.mocks[0].call_count, 2)

    def test_missing_contract_sheets(self):
        with self.assertRaisesMessage(ValueError, 'ไม่พบชีทสัญญา'):
            self.parse([], sheet='Sheet1')

    def test_missing_required_column(self):
        with self.assertRaisesMessage(ValueError, 'หาคอลัมน์ไม่เจอ'):
            self.parse([], headers=HEADERS[:-1])
