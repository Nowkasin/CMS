"""เมนูค่าล้างจาน -- SQL Server mock ทั้งหมด"""
import datetime
import importlib
import time
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory
from django.urls import resolve

from meters import log_middleware, permission_middleware
from meters.permissions import ACCESS_CHECKED_AT_KEY
from meters.services import activity_log, dishwash as service
from meters.services import invoice as invoice_service

from .helpers import NoDbTestCase, fake_connection

view_module = importlib.import_module('meters.views.dishwash')


def make_request(path='/dishwash/', method='get', data=None, permissions=None):
    req = getattr(RequestFactory(), method)(path, data or {}, HTTP_HOST='localhost')
    req.user = User(username='kasin.t')
    req.session = SessionStore()
    req.session['cms_permissions'] = permissions if permissions is not None else {'dishwash_fee': True}
    req.session[ACCESS_CHECKED_AT_KEY] = int(time.time())
    req.resolver_match = resolve(path.split('?')[0])
    return req


def row(**overrides):
    data = {
        'Contract_id': 12, 'Contract_code': 'A1/2568', 'Contract_year': '2568', 'Status_contract_id': '1',
        'Status_contract_Desc': 'สัญญา', 'CompanyName': 'ร้านทดสอบ', 'Dishwash_id': None, 'Amount': None,
        'Remark': None, 'Contract_fi_doc': None, 'Contract_fi_date': None, 'Saved_by': None, 'Saved_at': None,
    }
    data.update(overrides)
    return data


class DishwashViewTests(NoDbTestCase):
    def render(self, req, rows=None, save=None):
        with mock.patch.object(service, 'fetch_dishwash_month', return_value=rows or [row()]) as fetch, \
                mock.patch.object(service, 'save_dishwash_month', **(save or {'return_value': {
                    'created': [], 'updated': [], 'deleted': [], 'locked': []}})) as saver:
            resp = view_module.dishwash(req)
        return resp, fetch, saver

    def test_list_defaults_to_current_month(self):
        resp, fetch, _ = self.render(make_request())
        today = datetime.date.today()
        fetch.assert_called_once_with(today.year + 543, today.month, '')
        body = resp.content.decode()
        self.assertIn('ค่าล้างจาน', body)
        self.assertIn('name="amount_12"', body)
        self.assertIn('name="contract_ids" value="12"', body)

    def test_locked_row_has_no_input(self):
        locked = row(Dishwash_id=5, Amount=Decimal('300'), Contract_fi_doc='2100009999')
        body = self.render(make_request(), rows=[locked])[0].content.decode()
        self.assertNotIn('name="amount_12"', body)
        self.assertNotIn('name="contract_ids" value="12"', body)
        self.assertIn('ตั้งหนี้แล้ว', body)
        self.assertIn('2100009999', body)
        self.assertIn('300.00', body)

    def test_save_parses_amounts_and_redirects(self):
        req = make_request(method='post', data={
            'year': '2569', 'month': '11', 'q': 'A1',
            'contract_ids': ['12', '13', 'x'],
            'amount_12': '1,250.5', 'remark_12': ' ล้างจานงานเลี้ยง ',
            'amount_13': '',
        })
        result = {'created': [{'contract_id': 12, 'contract_code': 'A1/2568', 'amount': Decimal('1250.50')}],
                  'updated': [], 'deleted': [], 'locked': []}
        resp, _, saver = self.render(req, save={'return_value': result})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('saved=1', resp.url)
        self.assertIn('c=1', resp.url)
        self.assertIn('q=A1', resp.url)
        year, month, entries, user = saver.call_args.args
        self.assertEqual((year, month, user), (2569, 11, 'kasin.t'))
        self.assertEqual(entries, [
            {'contract_id': 12, 'amount': Decimal('1250.50'), 'remark': 'ล้างจานงานเลี้ยง'},
            {'contract_id': 13, 'amount': None, 'remark': ''},
        ])
        self.assertEqual(req.activity_result['dishwash'], result)

    def test_invalid_amounts_block_save(self):
        req = make_request(method='post', data={
            'year': '2569', 'month': '11', 'contract_ids': ['12', '13', '14', '15'],
            'code_12': 'A1', 'amount_12': 'abc',
            'code_13': 'A2', 'amount_13': '-5',
            'code_14': 'A3', 'amount_14': '1.234',
            'code_15': 'A4', 'amount_15': '', 'remark_15': 'มีหมายเหตุแต่ไม่มียอด',
        })
        resp, _, saver = self.render(req)
        saver.assert_not_called()
        body = resp.content.decode()
        for text in ('สัญญา A1: ยอดเงินต้องเป็นตัวเลข', 'สัญญา A2: ยอดเงินต้องไม่ติดลบ',
                     'สัญญา A3: ทศนิยมได้ไม่เกิน 2 ตำแหน่ง', 'สัญญา A4: กรอกหมายเหตุแล้วต้องกรอกยอดเงินด้วย'):
            self.assertIn(text, body)

    def test_invalid_period_blocks_save(self):
        req = make_request(method='post', data={'year': '2569', 'month': '13', 'contract_ids': ['12'],
                                                'amount_12': '10'})
        resp, _, saver = self.render(req)
        saver.assert_not_called()
        self.assertIn('เดือน ต้องไม่เกิน 12', resp.content.decode())

    def test_db_error_on_save(self):
        req = make_request(method='post', data={'year': '2569', 'month': '11', 'contract_ids': ['12'],
                                                'amount_12': '10'})
        resp, _, _ = self.render(req, save={'side_effect': RuntimeError('db')})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('บันทึกไม่สำเร็จ', resp.content.decode())

    def test_saved_banner_reports_locked(self):
        body = self.render(make_request('/dishwash/?year=2569&month=11&saved=1&c=2&u=1&d=0&l=1'))[0].content.decode()
        self.assertIn('เพิ่ม 2 · แก้ 1 · ลบ 0 สัญญา', body)
        self.assertIn('มี 1 สัญญาที่ตั้งหนี้ SAP แล้ว', body)

    def test_menu_requires_permission(self):
        mw = permission_middleware.CMSMenuPermissionMiddleware(lambda r: HttpResponse())
        self.assertIsNone(mw.process_view(make_request(), None, (), {}))
        denied = make_request(permissions={'invoice_print': True})
        self.assertEqual(mw.process_view(denied, None, (), {}).status_code, 404)


class DishwashServiceTests(NoDbTestCase):
    def run_save(self, existing, entries):
        """existing = แถวที่ SELECT ตรวจสอบคืน (Dishwash_id, Amount, Remark, fi_doc, code)"""
        def handler(sql, params):
            return existing if 'UPDLOCK' in sql else None
        conn, cursor = fake_connection(handler)
        with mock.patch.object(service, 'get_db_connection', return_value=conn):
            result = service.save_dishwash_month(2569, 11, entries, 'kasin.t')
        return result, cursor, conn

    def test_insert_new_row(self):
        result, cursor, conn = self.run_save((None, None, None, None, 'A1/2568'),
                                             [{'contract_id': 12, 'amount': Decimal('100.00'), 'remark': ''}])
        self.assertEqual(len(result['created']), 1)
        self.assertIn('INSERT INTO dbo.Contract_dishwash_tr', cursor.executed[1][0])
        self.assertEqual(cursor.executed[1][1][:6], (12, 'A1/2568', 2569, 11, Decimal('100.00'), None))
        conn.commit.assert_called_once()

    def test_locked_row_is_skipped(self):
        result, cursor, _ = self.run_save((5, Decimal('300'), None, '2100009999', 'A1/2568'),
                                          [{'contract_id': 12, 'amount': Decimal('100.00'), 'remark': ''}])
        self.assertEqual(result['locked'][0]['amount'], Decimal('300'))
        self.assertEqual(len(cursor.executed), 1)          # อ่านอย่างเดียว ไม่ UPDATE

    def test_unchanged_row_is_not_rewritten(self):
        result, cursor, _ = self.run_save((5, Decimal('100.00'), 'x', None, 'A1/2568'),
                                          [{'contract_id': 12, 'amount': Decimal('100.00'), 'remark': 'x'}])
        self.assertEqual(result, {'created': [], 'updated': [], 'deleted': [], 'locked': []})
        self.assertEqual(len(cursor.executed), 1)

    def test_blank_amount_deletes_unposted_row(self):
        result, cursor, _ = self.run_save((5, Decimal('100.00'), None, None, 'A1/2568'),
                                          [{'contract_id': 12, 'amount': None, 'remark': ''}])
        self.assertEqual(result['deleted'][0]['amount'], Decimal('100.00'))
        sql, params = cursor.executed[1]
        self.assertIn('DELETE FROM dbo.Contract_dishwash_tr', sql)
        self.assertIn('Contract_fi_doc IS NULL', sql)
        self.assertEqual(params, (5,))

    def test_db_error_rolls_back(self):
        def handler(sql, params):
            if 'INSERT' in sql:
                raise RuntimeError('db')
            return (None, None, None, None, 'A1')
        conn, _ = fake_connection(handler)
        with mock.patch.object(service, 'get_db_connection', return_value=conn):
            with self.assertRaises(RuntimeError):
                service.save_dishwash_month(2569, 11, [{'contract_id': 1, 'amount': Decimal('1'), 'remark': ''}], 'u')
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_list_query_is_parameterized(self):
        conn, cursor = fake_connection(lambda sql, params: [])
        cursor.description = [('Contract_id',)]
        with mock.patch.object(service, 'get_db_connection', return_value=conn):
            service.fetch_dishwash_month(2569, 11, "A1'; DROP")
        sql, params = cursor.executed[0]
        self.assertNotIn('DROP', sql)
        self.assertEqual(params[:2], (2569, 11))
        self.assertIn('Contract_dishwash_tr', sql)


class DishwashLogAndInvoiceTests(NoDbTestCase):
    def test_log_lists_changes(self):
        req = make_request(method='post')
        req.activity_result = {'year_be': 2569, 'month': 11, 'dishwash': {
            'created': [{'contract_id': 12, 'contract_code': 'A1/2568', 'amount': Decimal('100')}],
            'updated': [{'contract_id': 13, 'contract_code': 'A2/2568', 'amount': Decimal('80'),
                         'old_amount': Decimal('50')}],
            'deleted': [], 'locked': [{'contract_id': 14, 'contract_code': 'A3', 'amount': Decimal('9')}]}}
        data = log_middleware._dishwash_build(req, {}, None, HttpResponseRedirect('/'))
        self.assertEqual(data['action'], activity_log.ACTION_DISHWASH_SAVE)
        self.assertEqual(data['ref_text'], 'รอบบิล 11/2569 · 2 สัญญา')
        self.assertIn('เพิ่ม A1/2568 100.00', data['detail'])
        self.assertIn('แก้ A2/2568 50.00 → 80.00', data['detail'])
        self.assertNotIn('A3', data['detail'])

    def test_nothing_changed_is_not_logged(self):
        req = make_request(method='post')
        req.activity_result = {'dishwash': {'created': [], 'updated': [], 'deleted': [], 'locked': []}}
        self.assertIsNone(log_middleware._dishwash_build(req, {}, None, HttpResponseRedirect('/')))

    def test_log_visible_to_dishwash_group(self):
        self.assertIn(activity_log.ACTION_DISHWASH_SAVE,
                      activity_log.allowed_actions_for({'dishwash_fee': True}))

    def test_invoice_includes_posted_dishwash(self):
        self.assertIn('FROM dbo.Contract_dishwash_tr dw', invoice_service._LINES_CTE)
        self.assertIn("N'11'", invoice_service._LINES_CTE)
