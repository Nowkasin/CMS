from unittest import mock

from meters.services import meter_import

from .helpers import NoDbTestCase, fake_connection


def staged_row(idx=1, **extra):
    row = {
        'idx': idx, 'status': 'ok', 'message': '', 'type_cd': 9, 'type_label': 'น้ำ',
        'location_id': 'L1', 'area_id': 'A1', 'subarea_id': f'S{idx}',
        'meter_no': f'M{idx}', 'meter_no_status': 'ปกติ', 'phase_type': None,
        'db_contract_id': 99, 'contract_code': 'C1',
        'reading_before': 10, 'reading_after': 20,
    }
    row.update(extra)
    return row


def db_handler(fail_on=None):
    """จำลอง SP: Meter_Save คืน Meter_id, Reading_Save คืน Reading_id, ที่เหลือไม่คืนแถว"""
    def handler(sql, params):
        if fail_on and fail_on in sql:
            raise RuntimeError('[SQL Server] raw driver error')
        if 'sp_Contract_Meter_Save' in sql:
            return (555,)
        if 'sp_Contract_Meter_Reading_Save' in sql:
            return (777,)
        return None
    return handler


class CommitStagedRowsTests(NoDbTestCase):
    def run_commit(self, rows, fail_on=None):
        conn, cursor = fake_connection(db_handler(fail_on))
        with mock.patch.object(meter_import, 'get_db_connection', return_value=conn):
            result = meter_import.commit_staged_rows(
                rows, 'tester', source_filename='f.xlsx', billing_period='พฤศจิกายน 2569',
                billing_month=11, billing_year_be=2569,
            )
        return conn, cursor, result

    def test_success_commits_once_with_log_in_same_transaction(self):
        conn, cursor, result = self.run_commit([staged_row(1), staged_row(2, status='skip')])
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        self.assertEqual(result['stats']['meter_ok'], 1)
        self.assertEqual(result['stats']['reading_ok'], 1)
        self.assertEqual(result['stats']['skipped'], 1)
        self.assertTrue(any('sp_Contract_Activity_Log_Add' in sql for sql, _ in cursor.executed))

    def test_failure_in_any_step_rolls_back_whole_file(self):
        # เดิม: meter ของแถวที่ bind ล้มถูก commit ไปครึ่งเดียว และแถวถูกนับทั้งสำเร็จและ error
        with self.assertRaises(meter_import.ImportRowError) as ctx:
            self.run_commit([staged_row(1), staged_row(2)], fail_on='BindToContract')
        err = ctx.exception
        self.assertEqual(err.row_idx, 1)
        self.assertIn('แถวที่ 1', err.user_message())
        # ข้อความดิบจาก driver ต้องไม่หลุดไปถึงผู้ใช้
        self.assertNotIn('SQL Server', err.user_message())

    def test_failure_does_not_commit(self):
        conn, cursor = fake_connection(db_handler('Reading_Save'))
        with mock.patch.object(meter_import, 'get_db_connection', return_value=conn):
            with self.assertRaises(meter_import.ImportRowError):
                meter_import.commit_staged_rows([staged_row(1)], 'tester',
                                                billing_month=11, billing_year_be=2569)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_missing_meter_id_from_sp_is_an_error(self):
        def handler(sql, params):
            return None   # SP ไม่คืน Meter_id
        conn, _ = fake_connection(handler)
        with mock.patch.object(meter_import, 'get_db_connection', return_value=conn):
            with self.assertRaises(meter_import.ImportRowError):
                meter_import.commit_staged_rows([staged_row(1)], 'tester')
        conn.commit.assert_not_called()

    def test_parse_errors_are_reported_not_written(self):
        conn, cursor, result = self.run_commit([staged_row(1, status='error', message='ผิด')])
        self.assertEqual(result['stats']['errors'], 1)
        self.assertFalse(any('Meter_Save' in sql for sql, _ in cursor.executed))
