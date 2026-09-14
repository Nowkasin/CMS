# meters/services/__init__.py
"""
Re-export ทุกฟังก์ชัน/ค่าคงที่จากโมดูลย่อย เพื่อให้โค้ดเดิมที่เรียก services.xxx()
(เช่นใน views.py) ยังทำงานได้เหมือนเดิมทุกจุด โดยไม่ต้องแก้ import ที่อื่นเลย

โครงสร้างไฟล์:
  db.py            -> get_db_connection()
  excel_import.py  -> STATUS_MAP, COL_KEYS, parse_excel_staged, build_column_map,
                       find_contract_sheet, find_subarea, find_contract_by_code
  meters.py        -> fetch_*, save_*, commit_staged_rows, sp_meter_save,
                       sp_bind_to_contract, DEFAULT_USER
  excel_export.py  -> build_subareas_workbook
  termination.py   -> find_contract_for_termination, save_termination,
                       fetch_termination_detail, set_installment_selection
  download.py      -> fetch_contracts_for_download
"""
from .db import get_db_connection

from .excel_import import (
    STATUS_MAP,
    COL_KEYS,
    build_column_map,
    find_subarea,
    find_contract_by_code,
    find_contract_sheet,
    parse_excel_staged,
)

from .meters import (
    DEFAULT_USER,
    sp_meter_save,
    sp_bind_to_contract,
    commit_staged_rows,
    fetch_subareas,
    fetch_contract_meter_detail,
    fetch_subarea_meters,
    save_subarea_meters,
    fetch_readings_for_meters,
    fetch_meters,
    fetch_dashboard_stats,
    save_meter_reading,
)

from .excel_export import build_subareas_workbook

from .termination import (
    find_contract_for_termination,
    save_termination,
    fetch_termination_detail,
    set_installment_selection,
)

from .download import fetch_contracts_for_download

__all__ = [
    'get_db_connection',
    'STATUS_MAP', 'COL_KEYS', 'build_column_map', 'find_subarea',
    'find_contract_by_code', 'find_contract_sheet', 'parse_excel_staged',
    'DEFAULT_USER', 'sp_meter_save', 'sp_bind_to_contract', 'commit_staged_rows',
    'fetch_subareas', 'fetch_contract_meter_detail', 'fetch_subarea_meters',
    'save_subarea_meters', 'fetch_readings_for_meters', 'fetch_meters',
    'fetch_dashboard_stats', 'save_meter_reading',
    'build_subareas_workbook',
    'find_contract_for_termination', 'save_termination',
    'fetch_termination_detail', 'set_installment_selection',
    'fetch_contracts_for_download',
]