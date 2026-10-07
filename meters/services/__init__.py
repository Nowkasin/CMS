# meters/services/__init__.py
"""
Re-export ทุกฟังก์ชัน/ค่าคงที่จากโมดูลย่อย เพื่อให้โค้ดเดิมที่เรียก services.xxx()
(เช่นใน views.py) ยังทำงานได้เหมือนเดิมทุกจุด โดยไม่ต้องแก้ import ที่อื่นเลย

โครงสร้างไฟล์:
  db.py            -> get_db_connection()
  excel_import.py  -> STATUS_MAP, COL_KEYS, parse_excel_staged, build_column_map,
                       find_contract_sheet, find_subarea, find_contract_by_code,
                       find_registered_meter
  meters.py        -> fetch_*, save_*, commit_staged_rows, sp_meter_save,
                       sp_bind_to_contract, find_existing_meter, DEFAULT_USER,
                       fetch_meter_by_id, save_standalone_meter
  excel_export.py  -> build_subareas_workbook
  termination.py   -> fetch_contracts_for_termination, fetch_contract_statuses,
                       save_termination, delete_termination, fetch_termination_detail,
                       close_meter_billing, count_meter_bindings,
                       set_installment_selection, set_all_installment_selections,
                       fetch_contract_summary, BLOCKED_CONTRACT_STATUSES
  download.py      -> fetch_contracts_for_download
  phase.py         -> fetch_phase_types, fetch_phase_options, fetch_phase_type_by_id,
                       save_phase_type, MAX_PHASE_TYPE_LEN
"""
from .db import get_db_connection

from .excel_import import (
    STATUS_MAP,
    COL_KEYS,
    build_column_map,
    find_subarea,
    find_contract_by_code,
    find_contract_sheet,
    find_registered_meter,
    parse_excel_staged,
)

from .meters import (
    DEFAULT_USER,
    sp_meter_save,
    sp_bind_to_contract,
    find_existing_meter,
    commit_staged_rows,
    fetch_subareas,
    fetch_contract_meter_detail,
    fetch_subarea_meters,
    save_subarea_meters,
    fetch_readings_for_meters,
    fetch_meters,
    fetch_dashboard_stats,
    save_meter_reading,
    fetch_meter_by_id,
    save_standalone_meter,
)

from .excel_export import build_subareas_workbook

from .termination import (
    BLOCKED_CONTRACT_STATUSES,
    fetch_contracts_for_termination,
    fetch_contract_statuses,
    fetch_contract_summary,
    save_termination,
    delete_termination,
    close_meter_billing,
    count_meter_bindings,
    fetch_termination_history,
    fetch_termination_log,
    TERMINATION_LOG_EVENTS,
    fetch_termination_detail,
    set_installment_selection,
    set_all_installment_selections,
)

from .download import fetch_contracts_for_download

from .phase import (
    MAX_PHASE_TYPE_LEN,
    fetch_phase_types,
    fetch_phase_options,
    fetch_phase_type_by_id,
    save_phase_type,
)

__all__ = [
    'get_db_connection',
    'STATUS_MAP', 'COL_KEYS', 'build_column_map', 'find_subarea',
    'find_contract_by_code', 'find_contract_sheet', 'find_registered_meter',
    'parse_excel_staged',
    'DEFAULT_USER', 'sp_meter_save', 'sp_bind_to_contract',
    'find_existing_meter', 'commit_staged_rows',
    'fetch_subareas', 'fetch_contract_meter_detail', 'fetch_subarea_meters',
    'save_subarea_meters', 'fetch_readings_for_meters', 'fetch_meters',
    'fetch_dashboard_stats', 'save_meter_reading',
    'fetch_meter_by_id', 'save_standalone_meter',
    'build_subareas_workbook',
    'BLOCKED_CONTRACT_STATUSES',
    'fetch_contracts_for_termination', 'fetch_contract_statuses',
    'fetch_contract_summary',
    'delete_termination', 'close_meter_billing', 'count_meter_bindings',
    'fetch_termination_history', 'fetch_termination_log', 'TERMINATION_LOG_EVENTS',
    'save_termination',
    'fetch_termination_detail', 'set_installment_selection',
    'set_all_installment_selections',
    'fetch_contracts_for_download',
    'MAX_PHASE_TYPE_LEN', 'fetch_phase_types', 'fetch_phase_options',
    'fetch_phase_type_by_id', 'save_phase_type',
]