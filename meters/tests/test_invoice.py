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


def make_request(path):
    req = RequestFactory().get(path, **HOST)
    req.user = User(username='kasin.t')
    req.session = SessionStore()
    req.session['cms_permissions'] = {'invoice_print': True}
    req.session['cms_display_name'] = 'นายทดสอบ ระบบ'
    req.resolver_match = resolve(path.split('?')[0])
    return req


SAMPLE_ROW = {
    'Contract_id': 1234, 'Contract_code': 'AW7/2567', 'Contract_year': '2568', 'Contract_Installment_seq': 23,
    'Contract_debt_desc': 'ตั้งหนี้', 'Contract_Installment_month_year': '202611',
    'Contract_type_price_desc': 'ค่าใช้พื้นที่รายเดือน', 'Contract_duedate': datetime.date(2026, 11, 1),
    'Amount': Decimal('12000.00'), 'Contract_debt_to_SAP': '1', 'Contract_meeting_adj': None,
    'Contract_fi_doc': '2100000343', 'Contract_fi_date': datetime.date(2026, 11, 3),
    'Contract_owner': 'thanawath', 'Contract_swu_location_name': 'องครักษ์', 'CompanyName': 'บริษัท เฟรช มี จำกัด',
}

SP_ROW = {
    'NO': 1, 'Contract_code': 'AS1/2567', 'Contract_id': 1100, 'Contract_type_price_desc': 'ค่าใช้พื้นที่รายเดือน',
    'Doc Header Text': 'ค่าใช้พื้นที่รายเดือน', 'Contract_Installment_month_year': '202611',
    'Contract_Installment_amt': Decimal('36300.00'), 'Contract_swu_location_name': 'องครักษ์',
    'Contract_swu_address': 'เลขที่ 63 หมู่ที่ 7 ตำบลองครักษ์', 'Contract_fi_doc': '2100000341',
    'Contract_fi_date': datetime.date(2026, 11, 3), 'fiscal_year': 2027,
    'Contract_fi_date_thai': '3 พฤศจิกายน 2569', 'SAPVendor_Id': '1100000327',
    'CompanyName': 'บริษัท ซีพี ออลล์ จำกัด (มหาชน)', 'customer_address': '313 สีลม กรุงเทพมหานคร 10500',
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


class InvoiceServiceTests(NoDbTestCase):
    def test_search_builds_parameterized_filters(self):
        conn, cursor = fake_connection(lambda sql, params: [])
        cursor.description = [('Contract_id',)]
        with mock.patch.object(invoice_service, 'get_db_connection', return_value=conn):
            invoice_service.search_invoices('2568', '202611', 'AW7', None, None, 'องครักษ์', 'เฟรช')
        sql, params = cursor.executed[0]
        self.assertIn('a.Contract_fi_doc IS NOT NULL', sql)
        self.assertIn("a.Contract_type_price_id <> '7'", sql)
        self.assertEqual(params[:2], ('2568', '202611'))
        self.assertIn('%AW7%', params)
        self.assertNotIn('2568', sql)   # ค่าจากผู้ใช้ไม่ถูกต่อเข้า SQL

    def test_documents_group_lines_and_skip_missing(self):
        def handler(sql, params):
            return [tuple(SP_ROW.values())] if params[1] == '2100000341' else []
        conn, cursor = fake_connection(handler)
        cursor.description = [(k,) for k in SP_ROW]
        with mock.patch.object(invoice_service, 'get_db_connection', return_value=conn):
            docs = invoice_service.fetch_invoice_documents([('1100', '2100000341'), ('1, 2', 'x'), ('9', 'missing')])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['total'], Decimal('36300.00'))
        self.assertIn('sp_6000_Contact_Doc_invoice', cursor.executed[0][0])


class InvoiceViewTests(NoDbTestCase):
    def setUp(self):
        patches = [
            mock.patch.object(invoice_service, 'fetch_invoice_years', return_value=['2568', '2567']),
            mock.patch.object(invoice_service, 'fetch_invoice_locations', return_value=['องครักษ์']),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_first_visit_does_not_query(self):
        with mock.patch.object(invoice_service, 'search_invoices') as search:
            resp = invoice_view.invoice_search(make_request('/invoice/'))
        search.assert_not_called()
        self.assertEqual(resp.status_code, 200)

    def test_year_is_required_and_period_validated(self):
        with mock.patch.object(invoice_service, 'search_invoices') as search:
            body = invoice_view.invoice_search(make_request('/invoice/?year=&period=2026')).content.decode()
        search.assert_not_called()
        self.assertIn('กรุณาเลือกปีที่สร้างสัญญา', body)
        self.assertIn('ประจำงวดต้องเป็นตัวเลข 6 หลัก', body)

    def test_search_lists_rows_with_doc_key(self):
        with mock.patch.object(invoice_service, 'search_invoices', return_value=[dict(SAMPLE_ROW)]) as search:
            body = invoice_view.invoice_search(make_request('/invoice/?year=2568&period=202611')).content.decode()
        search.assert_called_once()
        self.assertIn('value="1234:2100000343"', body)
        self.assertIn('พฤศจิกายน 2569', body)
        self.assertIn('12,000.00', body)

    def test_db_error_shows_message(self):
        with mock.patch.object(invoice_service, 'search_invoices', side_effect=RuntimeError('db')):
            body = invoice_view.invoice_search(make_request('/invoice/?year=2568')).content.decode()
        self.assertIn('ค้นหาไม่สำเร็จ', body)

    def test_print_page_renders_invoice(self):
        doc = {'contract_id': '1100', 'fi_doc': '2100000341', 'header': dict(SP_ROW),
               'lines': [dict(SP_ROW)], 'total': Decimal('36300.00')}
        req = make_request('/invoice/print/?doc=1100:2100000341&doc=bad&doc=1100:2100000341')
        with mock.patch.object(invoice_service, 'fetch_invoice_documents', return_value=[doc]) as fetch:
            body = invoice_view.invoice_print(req).content.decode()
        fetch.assert_called_once_with([('1100', '2100000341')])   # ค่าซ้ำ/ผิดรูปแบบถูกตัด
        for text in ('2100000341 / 2027', '3 พฤศจิกายน 2569', '1100000327', 'AS1/2567',
                     'สามหมื่นหกพันสามร้อยบาทถ้วน', '36,300.00', 'นายทดสอบ ระบบ'):
            self.assertIn(text, body)
        self.assertEqual(req.activity_result, {'invoice_docs': ['2100000341']})

    def test_print_without_docs_redirects(self):
        resp = invoice_view.invoice_print(make_request('/invoice/print/'))
        self.assertEqual(resp.status_code, 302)


class InvoicePrintLogTests(NoDbTestCase):
    def test_print_is_logged(self):
        req = make_request('/invoice/print/?doc=1100:2100000341')
        mw = log_middleware.ActivityLogMiddleware(lambda r: HttpResponse('ok'))
        with mock.patch.object(log_middleware.activity, 'log_activity_safe') as log:
            mw.process_view(req, None, (), {})
            req.activity_result = {'invoice_docs': ['2100000341']}
            mw(req)
        args, kwargs = log.call_args
        self.assertEqual(args[0], 'invoice_print')
        self.assertIn('2100000341', kwargs['detail'])
