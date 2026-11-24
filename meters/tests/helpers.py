"""ตัวช่วยร่วมของ test -- cursor/connection ปลอมแทน pyodbc"""
from unittest import mock

from django.test import SimpleTestCase, override_settings

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


class FakeCursor:
    """
    cursor ปลอม: handler(sql, params) คืนค่าที่ fetchone/fetchall จะได้
    (tuple = แถวเดียว, list = หลายแถว, None = ไม่มีแถว) หรือ raise เพื่อจำลอง error จาก DB
    """

    def __init__(self, handler=None):
        self.handler = handler or (lambda sql, params: None)
        self.executed = []
        self._result = None
        self.description = None

    def execute(self, sql, *params):
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = tuple(params[0])
        self.executed.append((sql, params))
        self._result = self.handler(sql, params)
        return self

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if self._result is None:
            return []
        return self._result if isinstance(self._result, list) else [self._result]


def fake_connection(handler=None):
    """คืน (connection mock, cursor) -- ตรวจ conn.commit / conn.rollback ได้จาก mock"""
    cursor = FakeCursor(handler)
    conn = mock.MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@override_settings(CACHES=LOCMEM_CACHE)
class NoDbTestCase(SimpleTestCase):
    """test ที่ไม่ต้องใช้ฐานข้อมูลใดๆ (รวมถึง SQLite ของ Django)"""
