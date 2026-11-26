from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, RequestFactory, override_settings

from .forms import SpaceDetailsForm
from .services import space_profile as service
from .views.space_profile import space_profile_preview


ALL_PERMISSIONS = {'space_profile_view': True}
ADMIN_ID = '9B148353-6383-40D7-B3B8-F04FC8C5A4C5'


class SpaceProfileTests(SimpleTestCase):
    period = date(2026, 5, 31)

    def setUp(self):
        settings_override = override_settings(SPACE_PROFILE_START_PERIOD='202605')
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.nav_patch = patch('meters.views.space_profile.get_period_navigation', return_value=(self.period, []))
        self.nav_patch.start()
        self.addCleanup(self.nav_patch.stop)
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value
        self.db_patch = patch.object(service, 'get_db_connection', return_value=self.conn)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        for name, value in (('_period_status', 'OPEN'), ('_working_date', self.period), ('_snapshot_rows', [])):
            stub = patch.object(service, name, return_value=value)
            stub.start()
            self.addCleanup(stub.stop)
        self.details = dict.fromkeys(service.DETAIL_FIELDS, 'value')

    def live_row(self):
        return {'SubArea_id': 'A1', 'Contract_id': 42, **self.details, 'details_complete': True}

    def test_filters_combine_and_include_missing_values(self):
        rows = [
            {'Business_Types_BI': ' retail ', 'Memo_Location': 'campus', 'Status_Area': 'occupied'},
            {'Business_Types_BI': 'retail', 'Memo_Location': 'other', 'Status_Area': 'occupied'},
            {'Business_Types_BI': None, 'Memo_Location': '', 'Status_Area': 'vacant'},
        ]
        options = service.space_filter_options(rows)
        self.assertIn(('missing', 'ไม่ระบุ'), options['business'])
        self.assertEqual(options['business'].count(('value:retail', 'retail')), 1)
        self.assertEqual(service.filter_space_rows(rows, {
            'business': 'value:retail', 'location': 'value:campus', 'area_status': 'value:occupied',
        }), rows[:1])
        self.assertEqual(service.filter_space_rows(rows, {'business': 'missing'}), rows[2:])

    def test_history_filters_keep_period_and_pagination_links(self):
        rows = [{**self.live_row(), 'SubArea_id': f'A{i:02}', 'Business_Types_BI': 'retail',
                 'Memo_Location': 'campus', 'Status_Area': 'occupied'} for i in range(22)]
        request = RequestFactory().get('/', {'tab': 'history', 'period': self.period.isoformat(),
            'business': 'value:retail', 'location': 'value:campus', 'area_status': 'value:occupied'})
        request.session = {'cms_permissions': ALL_PERMISSIONS}
        request.user = MagicMock(username='tester')
        with patch('meters.views.space_profile.get_period_navigation', return_value=(date(2026, 6, 30), [self.period])), patch('meters.views.space_profile.load_space_period', return_value={'rows': rows, 'closed': True, 'editable': False}) as load:
            response = space_profile_preview(request)
        load.assert_called_once_with(self.period)
        self.assertContains(response, 'พบ 22 จาก 22 รายการ')
        self.assertContains(response, 'business=value%3Aretail&amp;location=value%3Acampus&amp;area_status=value%3Aoccupied&amp;page=2')
        self.assertContains(response, 'data-custom-select-label="สถานที่ตั้ง"')

    def test_invalid_filter_does_not_show_unfiltered_rows(self):
        request = RequestFactory().get('/', {'business': 'value:unknown'})
        request.session = {'cms_permissions': ALL_PERMISSIONS}
        request.user = MagicMock(username='tester')
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [self.live_row()], 'closed': False, 'editable': True}):
            response = space_profile_preview(request)
        self.assertContains(response, 'พบ 0 จาก 1 รายการ')
        self.assertContains(response, 'ค่าตัวกรองไม่อยู่ในรอบข้อมูลนี้')

    def test_store_date_and_area_details_merge(self):
        self.cursor.description = [('SubArea_id',)]
        self.cursor.fetchall.side_effect = [[('A1',)], [('A1', '1', 'food', 'retail', 'shop', 'purpose', None)]]
        original_execute = self.cursor.execute

        def execute(sql, *params):
            self.cursor.description = [(name,) for name in (
                ['SubArea_id'] if sql.startswith('EXEC') else ['SubArea_id', *service.DETAIL_FIELDS, 'Updated_at']
            )]
            return original_execute(sql, *params)

        with patch.object(self.cursor, 'execute', side_effect=execute):
            rows = service._live_rows(self.cursor, self.period)
        self.assertEqual(rows[0]['Floor_BI'], '1')
        self.assertTrue(rows[0]['details_complete'])
        original_execute.assert_any_call('EXEC dbo.SP_Contract_Location_SubArea_Test @c_date = ?', '20260531')

    def test_active_period_advances_and_rolls_year(self):
        self.assertEqual(service._active_date(None), self.period)
        self.assertEqual(service._active_date(self.period), date(2026, 6, 30))
        self.assertEqual(service._active_date(date(2026, 12, 31)), date(2027, 1, 31))

    def test_reopen_keeps_snapshot_and_records_reason(self):
        self.cursor.fetchone.return_value = (0,)
        with patch.object(service, '_period_status', return_value='CLOSED'), patch.object(service, '_snapshot_rows', return_value=[self.live_row()]):
            service.reopen_space_period(self.period, 'correct data', 'admin')
        queries = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertTrue(any('Revision_no = Revision_no + 1' in sql for sql in queries))
        self.assertFalse(any('DELETE' in sql or 'UPDATE dbo.Contract_Location_Snapshot' in sql for sql in queries))
        self.conn.commit.assert_called_once()

    def test_reopen_requires_reason_and_rejects_already_open(self):
        with self.assertRaises(service.SpaceProfileError):
            service.reopen_space_period(self.period, '', 'admin')
        self.cursor.fetchone.return_value = (0,)
        with self.assertRaises(service.SpaceProfileError):
            service.reopen_space_period(self.period, 'reason', 'admin')
        self.conn.commit.assert_not_called()

    def test_reopened_edit_updates_only_that_snapshot(self):
        self.cursor.fetchone.return_value = (0,)
        with patch.object(service, '_snapshot_rows', return_value=[self.live_row()]), patch.object(service, '_live_rows') as live:
            service.save_space_details(self.period, 'A1', self.details, 'editor')
        queries = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertTrue(any('UPDATE dbo.Contract_Location_Snapshot' in sql for sql in queries))
        self.assertFalse(any('Contract_Location_Input' in sql for sql in queries))
        live.assert_not_called()
        self.conn.commit.assert_called_once()

    def test_reclose_does_not_insert_duplicate_snapshot(self):
        self.cursor.fetchone.return_value = (0,)
        with patch.object(service, '_snapshot_rows', return_value=[self.live_row()]), patch.object(service, '_live_rows') as live:
            service.close_space_period(self.period, 'admin')
        queries = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertFalse(any('INSERT dbo.Contract_Location_Snapshot' in sql for sql in queries))
        self.assertTrue(any("Period_status = 'CLOSED'" in sql for sql in queries))
        live.assert_not_called()

    def test_roles_cannot_post_actions_without_permission(self):
        for action in ('close', 'reopen'):
            request = RequestFactory().post('/', {'action': action})
            request.session = {'cms_permissions': ALL_PERMISSIONS}
            request.user = MagicMock(username='tester')
            with patch('meters.views.space_profile.get_period_navigation') as nav:
                self.assertEqual(space_profile_preview(request).status_code, 404)
            nav.assert_not_called()

    def test_edit_only_user_has_edit_link_without_close_button(self):
        request = RequestFactory().get('/')
        request.session = {'cms_permissions': {'space_profile_view': True, 'space_profile_edit': True}}
        request.user = MagicMock(username='editor')
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [self.live_row()], 'closed': False, 'editable': True}):
            response = space_profile_preview(request)
        self.assertContains(response, 'แก้ไขพื้นที่ A1')
        self.assertNotContains(response, 'name="action" value="close"')

    def test_menu_permission_allows_edit_in_open_period(self):
        request = RequestFactory().get('/')
        request.session = {'cms_permissions': ALL_PERMISSIONS}
        request.user = MagicMock(username='viewer')
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [self.live_row()], 'closed': False, 'editable': True}):
            response = space_profile_preview(request, subarea_id='A1')
        self.assertNotContains(response, '<fieldset disabled')
        self.assertContains(response, '>บันทึกข้อมูล</button>')

    def test_admin_settings_shows_buttons_and_reopens(self):
        from .views.system_settings import system_settings
        row = {'Period_date': self.period, 'Period_status': 'CLOSED', 'Revision_no': 0}
        session = {'cms_permissions': {'system_settings': True}, 'cms_groups': [{'id': ADMIN_ID}]}
        request = RequestFactory().get('/')
        request.session = session
        request.user = MagicMock(username='admin', is_authenticated=True)
        with patch('meters.views.system_settings.list_space_periods', return_value=[row]):
            response = system_settings(request)
        self.assertContains(response, '>เปิดรอบให้แก้ไข</span>')
        self.assertContains(response, 'data-confirm-yes="ยืนยันเปิดรอบ"')
        request = RequestFactory().post('/', {'period': '2026-05-31', 'action': 'reopen', 'reason': 'correct data'})
        request.session = session
        request.user = MagicMock(username='admin', is_authenticated=True)
        with patch('meters.views.system_settings.reopen_space_period') as reopen:
            response = system_settings(request)
        self.assertEqual(response.status_code, 302)
        reopen.assert_called_once_with(self.period, 'correct data', request.user.get_username())

    def test_settings_requires_both_admin_group_and_menu(self):
        from .views.system_settings import system_settings
        sessions = (
            {'cms_permissions': {'system_settings': True}, 'cms_groups': []},
            {'cms_permissions': ALL_PERMISSIONS, 'cms_groups': [{'id': ADMIN_ID}]},
            {'cms_permissions': {'space_period_manage': True}, 'cms_groups': [{'id': ADMIN_ID}]},
        )
        for session in sessions:
            for action in ('close', 'reopen'):
                request = RequestFactory().post('/', {'period': '2026-05-31', 'action': action})
                request.session = session
                request.user = MagicMock(is_authenticated=True, username='tester')
                with patch('meters.views.system_settings.close_space_period') as close, patch('meters.views.system_settings.reopen_space_period') as reopen:
                    self.assertEqual(system_settings(request).status_code, 404)
                close.assert_not_called()
                reopen.assert_not_called()

    def test_settings_close_uses_confirmed_period_and_redirects(self):
        from .views.system_settings import system_settings
        request = RequestFactory().post('/', {'period': '2026-05-31', 'action': 'close'})
        request.session = {'cms_permissions': {'system_settings': True}, 'cms_groups': [{'id': ADMIN_ID.lower()}]}
        request.user = MagicMock(is_authenticated=True, username='admin')
        with patch('meters.views.system_settings.close_space_period') as close:
            response = system_settings(request)
        self.assertEqual(response.status_code, 302)
        close.assert_called_once_with(self.period, request.user.get_username())

    def test_settings_invalid_reopen_keeps_database_unchanged(self):
        from .views.system_settings import system_settings
        request = RequestFactory().post('/', {'period': 'invalid', 'action': 'reopen', 'reason': ''})
        request.session = {'cms_permissions': {'system_settings': True}, 'cms_groups': [{'id': ADMIN_ID}]}
        request.user = MagicMock(is_authenticated=True, username='admin')
        with patch('meters.views.system_settings.list_space_periods', return_value=[]), patch('meters.views.system_settings.reopen_space_period') as reopen:
            response = system_settings(request)
        self.assertEqual(response.status_code, 200)
        reopen.assert_not_called()

    def test_settings_url_is_guarded_by_middleware(self):
        from types import SimpleNamespace
        from .permission_middleware import CMSMenuPermissionMiddleware
        middleware = CMSMenuPermissionMiddleware(lambda r: None)
        request = RequestFactory().get('/settings/')
        request.user = MagicMock(is_authenticated=True, username='tester')
        request.session = {'cms_permissions': {'system_settings': True}, 'cms_groups': [], 'cms_access_checked_at': 9999999999}
        request.resolver_match = SimpleNamespace(url_name='system_settings')
        self.assertEqual(middleware.process_view(request, None, (), {}).status_code, 404)
        request.session['cms_groups'] = [{'id': ADMIN_ID}]
        self.assertIsNone(middleware.process_view(request, None, (), {}))

    def test_cross_month_save_is_rejected_before_writing(self):
        self.cursor.fetchone.side_effect = [(0,), (None,)]
        with self.assertRaises(service.SpaceProfileError):
            service.save_space_details(date(2026, 6, 30), 'A1', self.details, 'tester')
        self.conn.commit.assert_not_called()
        self.conn.rollback.assert_called_once()

    def test_history_empty_does_not_load_live_data(self):
        request = RequestFactory().get('/', {'tab': 'history'})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.load_space_period') as load:
            response = space_profile_preview(request)
        self.assertContains(response, 'ยังไม่มีประวัติรายเดือน')
        load.assert_not_called()

    def test_history_only_loads_closed_period_and_cannot_save(self):
        nav = (date(2026, 6, 30), [self.period])
        loaded = {'rows': [self.live_row()], 'closed': True, 'editable': False}
        request = RequestFactory().get('/', {'tab': 'history', 'period': '2026-05-31'})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.get_period_navigation', return_value=nav), patch('meters.views.space_profile.load_space_period', return_value=loaded) as load:
            response = space_profile_preview(request)
        load.assert_called_once_with(self.period)
        self.assertContains(response, 'อ่านได้อย่างเดียว')
        payload = {'tab': 'history', 'period': '2026-05-31', 'action': 'save'}
        request = RequestFactory().post('/', payload)
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.get_period_navigation', return_value=nav), patch('meters.views.space_profile.load_space_period', return_value=loaded), patch('meters.views.space_profile.save_space_details') as save:
            space_profile_preview(request, subarea_id='A1')
        save.assert_not_called()

    def test_closed_period_reads_frozen_data_without_store(self):
        with patch.object(service, '_snapshot_rows', return_value=[self.live_row()]), patch.object(service, '_period_status', return_value='CLOSED'), patch.object(service, '_live_rows') as live:
            result = service.load_space_period(self.period)
        self.assertTrue(result['closed'])
        self.assertFalse(result['editable'])
        live.assert_not_called()

    def test_save_inserts_area_default_and_commits(self):
        self.cursor.fetchone.side_effect = [(0,), (0,)]
        with patch.object(service, '_live_rows', return_value=[self.live_row()]):
            service.save_space_details(self.period, 'A1', self.details, 'tester')
        insert = [call for call in self.cursor.execute.call_args_list if 'INSERT dbo.Contract_Location_Input' in call.args[0]]
        self.assertEqual(len(insert), 1)
        self.assertEqual(insert[0].args[1], 'A1')
        self.assertIn('VALUES (?, 0,', insert[0].args[0])
        self.conn.commit.assert_called_once()

    def test_save_existing_does_not_duplicate(self):
        self.cursor.fetchone.side_effect = [(0,), (1,)]
        with patch.object(service, '_live_rows', return_value=[self.live_row()]):
            service.save_space_details(self.period, 'A1', self.details, 'tester')
        self.assertFalse(any('INSERT' in c.args[0] for c in self.cursor.execute.call_args_list))

    def test_save_rejects_closed_period(self):
        self.cursor.fetchone.side_effect = [(0,), (self.period,)]
        with patch.object(service, '_period_status', return_value='CLOSED'), self.assertRaises(service.SpaceProfileError):
            service.save_space_details(self.period, 'A1', self.details, 'tester')
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_save_rejects_unknown_area(self):
        self.cursor.fetchone.side_effect = [(0,), (None,)]
        with patch.object(service, '_live_rows', return_value=[]), self.assertRaises(service.SpaceProfileError):
            service.save_space_details(self.period, 'unknown', self.details, 'tester')
        self.conn.rollback.assert_called_once()

    def test_close_copies_details_without_deleting_history(self):
        self.cursor.fetchone.side_effect = [(0,), (None,)]
        with patch.object(service, '_live_rows', return_value=[self.live_row()]):
            self.assertEqual(service.close_space_period(self.period, 'tester'), 1)
        inserts = [c for c in self.cursor.execute.call_args_list if 'INSERT dbo.Contract_Location_Snapshot' in c.args[0]]
        self.assertEqual(inserts[0].args[1], self.period)
        self.assertIn('value', inserts[0].args)
        self.assertFalse(any('DELETE' in c.args[0] for c in self.cursor.execute.call_args_list))
        self.conn.commit.assert_called_once()

    def test_close_empty_duplicate_or_database_error_rolls_back(self):
        for rows in ([], [self.live_row(), self.live_row()]):
            self.cursor.fetchone.side_effect = [(0,), (None,)]
            with patch.object(service, '_live_rows', return_value=rows), self.assertRaises(service.SpaceProfileError):
                service.close_space_period(self.period, 'tester')
        self.cursor.fetchone.side_effect = [(0,), (None,)]
        with patch.object(service, '_live_rows', side_effect=RuntimeError('DB error')), self.assertRaises(RuntimeError):
            service.close_space_period(self.period, 'tester')
        self.assertEqual(self.conn.rollback.call_count, 3)
        self.conn.commit.assert_not_called()

    def test_close_incomplete_preserves_blank_values(self):
        self.cursor.fetchone.side_effect = [(0,), (None,)]
        row = self.live_row()
        row.update(Floor_BI='', Shop_name_BI=None, details_complete=False)
        with patch.object(service, '_live_rows', return_value=[row]):
            self.assertEqual(service.close_space_period(self.period, 'tester'), 1)
        insert = next(c for c in self.cursor.execute.call_args_list if 'INSERT dbo.Contract_Location_Snapshot' in c.args[0])
        self.assertIn('', insert.args)
        self.assertIn(None, insert.args)
        self.conn.commit.assert_called_once()

    def test_business_page_has_no_period_action_forms(self):
        request = RequestFactory().get('/', {'month': 5, 'year': 2569})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS}
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [self.live_row()], 'closed': False, 'editable': True}):
            response = space_profile_preview(request)
        self.assertNotContains(response, 'name="action" value="close"')
        self.assertNotContains(response, 'name="action" value="reopen"')

    def test_form_requires_five_values_and_snapshot_length_limit(self):
        self.assertFalse(SpaceDetailsForm({}).is_valid())
        data = {'floor': '1', 'products': 'food', 'business_type': 'retail', 'shop_name': 'shop', 'purpose': 'purpose'}
        self.assertTrue(SpaceDetailsForm(data).is_valid())
        data['floor'] = 'x' * 11
        self.assertFalse(SpaceDetailsForm(data).is_valid())

    def test_insert_failure_rolls_back_save(self):
        self.cursor.fetchone.side_effect = [(0,), (0,)]
        self.cursor.execute.side_effect = [None, None, RuntimeError('insert failed')]
        with patch.object(service, '_live_rows', return_value=[self.live_row()]), self.assertRaises(RuntimeError):
            service.save_space_details(self.period, 'A1', self.details, 'tester')
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_invalid_post_cannot_write_and_post_error_keeps_input(self):
        payload = {'month': '5', 'year': '2569', 'subarea': 'A1', 'action': 'save', 'floor': '1'}
        period = {'rows': [self.live_row()], 'closed': False, 'editable': True}
        with patch('meters.views.space_profile.load_space_period', return_value=period), patch('meters.views.space_profile.save_space_details') as save:
            request = RequestFactory().post('/', payload)
            request.user = MagicMock(username='tester')
            request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
            response = space_profile_preview(request, subarea_id='A1')
            self.assertEqual(response.status_code, 200)
            save.assert_not_called()
            self.assertContains(response, 'value="1"')

    def test_query_error_shows_generic_message(self):
        request = RequestFactory().get('/', {'month': 5, 'year': 2569})
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        request.user = MagicMock(username='tester')
        with patch('meters.views.space_profile.load_space_period', side_effect=RuntimeError('secret connection info')):
            response = space_profile_preview(request)
        self.assertContains(response, 'ไม่สามารถโหลดข้อมูลพื้นที่ได้')
        self.assertNotContains(response, 'secret connection info')

    def test_list_shows_saved_fields_and_links_to_separate_detail(self):
        request = RequestFactory().get('/', {'month': 5, 'year': 2569})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        row = self.live_row()
        row['Shop_name_BI'] = 'Saved shop name'
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [row], 'closed': False, 'editable': True}):
            response = space_profile_preview(request)
        self.assertContains(response, 'Saved shop name')
        self.assertContains(response, '/spaces/details/A1/')
        self.assertContains(response, 'กรอกครบ')
        self.assertNotContains(response, 'name="floor"')

    def test_detail_save_returns_to_original_list_page(self):
        payload = {'month': '5', 'year': '2569', 'page': '3', 'action': 'save',
                   'floor': '1', 'products': 'food', 'business_type': 'retail',
                   'shop_name': 'shop', 'purpose': 'purpose', 'subarea': 'tampered'}
        request = RequestFactory().post('/', payload)
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.save_space_details') as save:
            response = space_profile_preview(request, subarea_id='A1')
        self.assertEqual(response.status_code, 302)
        self.assertIn('page=3', response.url)
        self.assertIn('result=save', response.url)
        self.assertNotIn('subarea=', response.url)
        self.assertEqual(save.call_args.args[1], 'A1')

    def test_closed_detail_is_readonly_and_keeps_return_period(self):
        request = RequestFactory().get('/', {'month': 5, 'year': 2569})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.load_space_period', return_value={'rows': [self.live_row()], 'closed': True, 'editable': False}):
            response = space_profile_preview(request, subarea_id='A1')
        self.assertContains(response, '<fieldset disabled', html=False)
        self.assertNotContains(response, '>บันทึกข้อมูล</button>')
        self.assertContains(response, 'month=5&amp;year=2569')

    def test_views_render_open_closed_empty_error_and_invalid_period(self):
        for closed, rows in ((False, [self.live_row()]), (True, [self.live_row()]), (False, [])):
            request = RequestFactory().get('/', {'month': 5, 'year': 2569, 'subarea': 'A1'})
            request.user = MagicMock(username='tester')
            request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
            with patch('meters.views.space_profile.load_space_period', return_value={'rows': rows, 'closed': closed, 'editable': not closed}):
                response = space_profile_preview(request)
            self.assertEqual(response.status_code, 200)
            if closed:
                self.assertNotContains(response, 'name="action" value="close"')
        request = RequestFactory().get('/', {'month': 99})
        request.user = MagicMock(username='tester')
        request.session = {'cms_permissions': ALL_PERMISSIONS.copy()}
        with patch('meters.views.space_profile.load_space_period') as load:
            self.assertEqual(space_profile_preview(request).status_code, 200)
            load.assert_not_called()
