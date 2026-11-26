import datetime
import importlib
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve

from meters import log_middleware
from meters.services import invoice as invoice_service
from meters.utils import baht_text

from .helpers import NoDbTestCase, fake_connection

invoice_view = importlib.import_module('meters.views.invoice')
HOST = {'HTTP_HOST': 'localhost'}
FI_DATE = datetime.date(2026, 6, 4)


def make_request(path):
    req = RequestFactory().get(path, **HOST)
    req.user = User(username='kasin.t')
    req.session = SessionStore()
    req.session['cms_permissions'] = {'invoice_print': True}
    req.session['cms_display_name'] = 'นายทดสอบ ระบบ'
    req.resolver_match = resolve(path.split('?')[0])
    return req


def line(**overrides):
    """บรรทัดจาก _LINES_CTE (ค่าเริ่มต้น = ค่าใช้พื้นที่รายเดือนจาก Contract_Installment_tr)"""
    row = {
        'Contract_id': 1234, 'Contract_fi_doc': '2100004064', 'Contract_fi_date': FI_DATE,
        'Contract_type_price_id': '1', 'Contract_type_price_desc': 'ค่าใช้พื้นที่รายเดือน',
        'Contract_debt_desc': 'ตั้งหนี้', 'Contract_debt_cd': '11', 'Period': '202606',
        'Amount': Decimal('2140.00'), 'Meter_no': None, 'Reading_before': None, 'Reading_after': None,
        'Contract_debt_to_SAP': '1', 'Contract_meeting_adj': None, 'Line_seq': 23, 'Line_source': 'I',
    }
    row.update(overrides)
    return row


def search_row(**overrides):
    row = line(Contract_code='A1/2568', Contract_year='2568', Contract_owner='thanawath',
               Contract_swu_location_name='ประสานมิตร', SAPVendor_Id='1200000223',
               CompanyName='นายวรวิทย์ มิตรอำพันธ์')
    row.update(overrides)
    return row


ELECTRIC = dict(Contract_fi_doc='2100004067', Contract_type_price_id='9', Contract_type_price_desc='ค่าไฟฟ้า',
                Contract_debt_desc=None, Contract_debt_cd=None, Period='202605', Amount=Decimal('492.00'),
                Meter_no='E-001', Reading_before=18368, Reading_after=18450, Line_seq=7, Line_source='M')

HEADER = {
    'Contract_code': 'A1/2568', 'Contract_year': '2568', 'Contract_swu_location_name': 'ประสานมิตร',
    'Contract_swu_address': 'เลขที่ 114 ซอยสุขุมวิท 23', 'SAPVendor_Id': '1200000223',
    'CompanyName': 'นายวรวิทย์ มิตรอำพันธ์', 'customer_address': '258/3 ประเสริฐสิษฐ์ วัฒนา กรุงเทพมหานคร 10110',
}


class BahtTextTests(NoDbTestCase):
    def test_examples(self):
        cases = {
            36300: 'สามหมื่นหกพันสามร้อยบาทถ้วน',
            101: 'หนึ่งร้อยเอ็ดบาทถ้วน',
            21: 'ยี่สิบเอ็ดบาทถ้วน',
            11: 'สิบเอ็ดบาทถ้วน',
            1: 'หนึ่งบาทถ้วน',
            1000001: 'หนึ่งล้านเอ็ดบาทถ้วน',
            2500000: 'สองล้านห้าแสนบาทถ้วน',
            0: 'ศูนย์บาทถ้วน',
            Decimal('120.50'): 'หนึ่งร้อยยี่สิบบาทห้าสิบสตางค์',
            Decimal('0.25'): 'ยี่สิบห้าสตางค์',
        }
        for amount, expected in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(baht_text(amount), expected)


class ScriptedCursor:
    """cursor ที่คืนแถว (dict) และ description ตามคำใน SQL -- แต่ละ query มีคอลัมน์ต่างกัน"""

    def __init__(self, script):
        self.script = script
        self.executed = []
        self.description = None
        self._rows = []

    def execute(self, sql, *params):
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = tuple(params[0])
        self.executed.append((sql, params))
        if callable(self.script):
            rows = self.script(sql, params)
        else:
            rows = next((rows for key, rows in self.script.items() if key in sql), [])
        columns = list(rows[0]) if rows else ['x']
        self.description = [(c,) for c in columns]
        self._rows = [tuple(row[c] for c in columns) for row in rows]

    def fetchall(self):
        return self._rows


class InvoiceServiceTests(NoDbTestCase):
    def search_sql(self, *args, **kwargs):
        conn, cursor = fake_connection(lambda sql, params: [])
        cursor.description = [('Contract_id',)]
        with mock.patch.object(invoice_service, 'get_db_connection', return_value=conn):
            result = invoice_service.search_invoices(*args, **kwargs)
        sql, params = cursor.executed[0]
        return result, sql, params

    def test_search_one_box_matches_many_fields(self):
        result, sql, params = self.search_sql('AW7', period='202611', location='องครักษ์')
        self.assertEqual(result, ([], False))
        for column in ('h.Contract_code', 'cu.CompanyName', 'cu.SAPVendor_Id', 'x.Contract_fi_doc LIKE ?'):
            self.assertIn(column, sql)
        self.assertEqual(params.count('%AW7%'), 4)
        # เดือนที่ตั้งหนี้ = ช่วงวันที่ของ Contract_fi_date
        self.assertIn(datetime.date(2026, 11, 1), params)
        self.assertIn(datetime.date(2026, 12, 1), params)
        self.assertNotIn('AW7', sql)   # ค่าจากผู้ใช้ไม่ถูกต่อเข้า SQL

    def test_december_period_ends_next_year(self):
        _result, _sql, params = self.search_sql(period='202612')
        self.assertEqual(params, (datetime.date(2026, 12, 1), datetime.date(2027, 1, 1)))

    def test_lines_include_deposit_utilities_and_meter_readings(self):
        _result, sql, _params = self.search_sql()
        self.assertNotIn('v_contract_price_tr', sql)
        self.assertNotIn("<> '7'", sql)                     # แบบร่างรวมค่าประกันสัญญาในใบ
        self.assertIn("i.Contract_type_price_id IN ('8', '9')", sql)
        self.assertIn('EXISTS (SELECT 1 FROM dbo.Contract_price_tr', sql)
        self.assertIn('dbo.Contract_meter_reading_tr rd', sql)
        self.assertIn('rd.Reading_before', sql)

    def test_search_without_filters_has_no_parameters(self):
        _result, _sql, params = self.search_sql()
        self.assertEqual(params, ())

    def test_search_reports_truncation(self):
        many = [(i,) for i in range(invoice_service.MAX_SEARCH_ROWS + 1)]
        conn, cursor = fake_connection(lambda sql, params: many)
        cursor.description = [('Contract_id',)]
        with mock.patch.object(invoice_service, 'get_db_connection', return_value=conn):
            rows, truncated = invoice_service.search_invoices()
        self.assertTrue(truncated)
        self.assertEqual(len(rows), invoice_service.MAX_SEARCH_ROWS)

    def fetch(self, cursor, keys):
        conn = mock.MagicMock()
        conn.cursor.return_value = cursor
        with mock.patch.object(invoice_service, 'get_db_connection', return_value=conn):
            return invoice_service.fetch_invoice_documents(keys)

    def test_document_combines_sap_docs_and_meter_lines(self):
        annual_sp = {'Contract_Installment_seq': Decimal('24'), 'Contract_debt_cd': '11',
                     'Doc Header Text': 'ค่าใช้พื้นที่รายปี : 01มิ.ย.69 - 31พ.ค.70'}
        lines = [line(), line(Contract_fi_doc='2100004065', Line_seq=24), line(**ELECTRIC)]
        cursor = ScriptedCursor(lambda sql, params: (
            [annual_sp] if 'sp_6000' in sql and params[1] == '2100004065'
            else [] if 'sp_6000' in sql
            else [HEADER] if 'v_contact_for_pdf' in sql
            else lines))
        docs = self.fetch(cursor, [('1234', FI_DATE, None)])
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc['docs'], ['2100004064', '2100004065', '2100004067'])
        self.assertEqual(doc['total'], Decimal('4772.00'))
        self.assertEqual(doc['header']['CompanyName'], HEADER['CompanyName'])
        self.assertEqual(doc['lines'][1]['Doc Header Text'], annual_sp['Doc Header Text'])
        self.assertIsNone(doc['lines'][2]['Doc Header Text'])      # บรรทัดมิเตอร์ไม่เรียก SP
        # SP เรียกเฉพาะเลขเอกสารของงวดใน Contract_Installment_tr
        sp_calls = [params for sql, params in cursor.executed if 'sp_6000' in sql]
        self.assertEqual(sp_calls, [('1234', '2100004064'), ('1234', '2100004065')])
        lines_sql, lines_params = cursor.executed[0]
        self.assertIn('l.Contract_fi_date = ?', lines_sql)
        self.assertEqual(lines_params, ('1234', FI_DATE))

    def test_document_without_date_uses_doc_number(self):
        cursor = ScriptedCursor(lambda sql, params: [HEADER] if 'v_contact_for_pdf' in sql
                                else [] if 'sp_6000' in sql else [line(Contract_fi_date=None)])
        docs = self.fetch(cursor, [('1234', None, '2100004064')])
        self.assertEqual(len(docs), 1)
        lines_sql, lines_params = cursor.executed[0]
        self.assertIn('l.Contract_fi_date IS NULL AND l.Contract_fi_doc = ?', lines_sql)
        self.assertEqual(lines_params, ('1234', '2100004064'))

    def test_missing_documents_are_skipped(self):
        cursor = ScriptedCursor(lambda sql, params: [])
        self.assertEqual(self.fetch(cursor, [('9', FI_DATE, None)]), [])


class InvoiceViewTests(NoDbTestCase):
    def setUp(self):
        patches = [
            mock.patch.object(invoice_service, 'fetch_invoice_periods', return_value=['202606', '202605']),
            mock.patch.object(invoice_service, 'fetch_invoice_years', return_value=['2568', '2567']),
            mock.patch.object(invoice_service, 'fetch_invoice_locations', return_value=['ประสานมิตร']),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def search(self, query, rows=None, **kwargs):
        mocked = mock.patch.object(invoice_service, 'search_invoices', return_value=(rows or [], False), **kwargs)
        with mocked as search:
            body = invoice_view.invoice_search(make_request('/invoice/' + query)).content.decode()
        return body, search

    def test_first_visit_shows_latest_month(self):
        body, search = self.search('', [search_row()])
        self.assertEqual(search.call_args.kwargs['period'], '202606')
        self.assertIn('value="1234:20260604"', body)
        self.assertIn('ใบแจ้งหนี้ · มิถุนายน 2569', body)

    def test_query_without_period_searches_all_months(self):
        _body, search = self.search('?q=วรวิทย์')
        self.assertEqual(search.call_args.kwargs['period'], '')
        self.assertEqual(search.call_args.kwargs['query'], 'วรวิทย์')

    def test_lines_of_same_contract_and_date_are_one_invoice(self):
        rows = [search_row(), search_row(Contract_fi_doc='2100004065', Line_seq=24, Amount=Decimal('10000.00')),
                search_row(**ELECTRIC),
                # สัญญาเดียวกันแต่ตั้งหนี้คนละวัน = อีกใบ
                search_row(Contract_fi_doc='2100003000', Contract_fi_date=datetime.date(2026, 5, 4))]
        body, _ = self.search('?period=all', rows)
        self.assertEqual(body.count('data-invoice-check'), 2)
        for text in ('2100004064', '2100004065', '2100004067', '12,632.00', '3 รายการ', 'มิเตอร์ E-001'):
            self.assertIn(text, body)

    def test_search_term_is_highlighted_and_escaped(self):
        body, _ = self.search('?q=วรวิทย์', [search_row(CompanyName='<b>นายวรวิทย์</b>')])
        self.assertIn('<mark', body)
        self.assertIn('&lt;b&gt;', body)
        self.assertNotIn('<b>นายวรวิทย์', body)

    def test_not_found_suggests_other_months(self):
        with mock.patch.object(invoice_service, 'search_invoices',
                               side_effect=[([], False), ([search_row()], False)]):
            body = invoice_view.invoice_search(make_request('/invoice/?q=A1&period=202605')).content.decode()
        self.assertIn('พบ 1 ใบในเดือนอื่น', body)

    def test_invalid_period_is_rejected(self):
        body, search = self.search('?period=2026')
        search.assert_not_called()
        self.assertIn('เดือนที่ตั้งหนี้ไม่ถูกต้อง', body)

    def test_db_error_shows_message(self):
        body, _ = self.search('?q=x', side_effect=RuntimeError('db'))
        self.assertIn('ค้นหาไม่สำเร็จ', body)

    def test_parse_doc_keys(self):
        keys = invoice_view.parse_doc_keys([
            '1234:20260604', '1234:20260604', '1234:N2100004064', '1234:20260231',   # 31 ก.พ. ไม่มีจริง
            'bad', '1234:2100004064', "1:N'; DROP",
        ])
        self.assertEqual(keys, [('1234', FI_DATE, None), ('1234', None, '2100004064')])

    def test_print_page_renders_invoice(self):
        doc = {'contract_id': '1234', 'fi_date': FI_DATE, 'docs': ['2100004064', '2100004067'],
               'header': dict(HEADER), 'total': Decimal('2632.00'),
               'lines': [line(**{'Doc Header Text': 'ค่าใช้พื้นที่รายเดือน'}), line(**ELECTRIC)]}
        req = make_request('/invoice/print/?doc=1234:20260604&doc=bad')
        with mock.patch.object(invoice_service, 'fetch_invoice_documents', return_value=[doc]) as fetch:
            body = invoice_view.invoice_print(req).content.decode()
        fetch.assert_called_once_with([('1234', FI_DATE, None)])
        for text in ('Document', 'มิเตอร์ก่อน', 'มิเตอร์หลัง', '2100004064', '2100004067', '18368', '18450',
                     'มิถุนายน 2569', 'พฤษภาคม 2569', '4 มิถุนายน 2569', '1200000223', 'A1/2568',
                     'สองพันหกร้อยสามสิบสองบาทถ้วน', '2,632.00', '492.00', 'นายทดสอบ ระบบ'):
            self.assertIn(text, body)
        self.assertNotIn('เลขที่ใบแจ้งหนี้', body)
        self.assertIn('meters/images/invoice-qr-payment.png', body)
        self.assertIn('meters/webfonts/THSarabunPSK-Regular.ttf', body)
        self.assertIn('meters/webfonts/THSarabunPSK-Bold.ttf', body)
        self.assertIn('มหาวิทยาลัยศรีนครินทรวิโรฒ ประสานมิตร', body)
        self.assertEqual(req.activity_result,
                         {'invoice_docs': ['2100004064', '2100004067'], 'invoice_count': 1})

    def test_full_location_name_is_not_repeated(self):
        header = dict(HEADER, Contract_swu_location_name='มหาวิทยาลัยศรีนครินทรวิโรฒ ประสานมิตร')
        doc = {'contract_id': '1234', 'fi_date': FI_DATE, 'docs': ['2100004064'], 'header': header,
               'total': Decimal('2140.00'), 'lines': [line()]}
        with mock.patch.object(invoice_service, 'fetch_invoice_documents', return_value=[doc]):
            body = invoice_view.invoice_print(make_request('/invoice/print/?doc=1234:20260604')).content.decode()
        self.assertNotIn('มหาวิทยาลัยศรีนครินทรวิโรฒ มหาวิทยาลัยศรีนครินทรวิโรฒ', body)
        self.assertIn('มหาวิทยาลัยศรีนครินทรวิโรฒ ประสานมิตร', body)

    def test_print_marks_test_copy_during_maintenance(self):
        doc = {'contract_id': '1234', 'fi_date': FI_DATE, 'docs': ['2100004064'], 'header': dict(HEADER),
               'total': Decimal('2140.00'), 'lines': [line()]}
        req = make_request('/invoice/print/?doc=1234:20260604')
        with mock.patch.object(invoice_service, 'fetch_invoice_documents', return_value=[doc]):
            normal = invoice_view.invoice_print(req).content.decode()
            req.cms_maintenance_bypass = True
            bypass = invoice_view.invoice_print(req).content.decode()
        self.assertNotIn('>ทดสอบ<', normal)
        self.assertIn('>ทดสอบ<', bypass)

    def test_print_without_docs_redirects(self):
        resp = invoice_view.invoice_print(make_request('/invoice/print/'))
        self.assertEqual(resp.status_code, 302)


class InvoicePrintLogTests(NoDbTestCase):
    def test_print_is_logged(self):
        req = make_request('/invoice/print/?doc=1234:20260604')
        mw = log_middleware.ActivityLogMiddleware(lambda r: HttpResponse('ok'))
        with mock.patch.object(log_middleware.activity, 'log_activity_safe') as log:
            mw.process_view(req, None, (), {})
            req.activity_result = {'invoice_docs': ['2100004064', '2100004067'], 'invoice_count': 1}
            mw(req)
        args, kwargs = log.call_args
        self.assertEqual(args[0], 'invoice_print')
        self.assertIn('พิมพ์ใบแจ้งหนี้ 1 ใบ', kwargs['detail'])
        self.assertIn('2100004064, 2100004067', kwargs['detail'])
