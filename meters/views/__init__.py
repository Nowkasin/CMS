# meters/views/__init__.py
"""
Re-export ทุก view จากโมดูลย่อย เพื่อให้ urls.py ที่เรียก views.xxx เหมือนเดิม
ยังทำงานได้ทุกจุดโดยไม่ต้องแก้ import

โครงสร้างไฟล์:
  steppage.py     -> step1_upload, edit_staged_row, step2_review, step3_confirm,
                      step4_done, restart
  dashboard.py    -> dashboard, edit_meter
  export.py       -> export_meters_excel
  termination.py  -> termination_search, termination_detail, termination_toggle_installment
  download.py     -> download_form, download_excel
  meter_master.py -> meter_list, meter_form
"""
from .steppage import (
    step1_upload,
    edit_staged_row,
    step2_review,
    step3_confirm,
    step4_done,
    restart,
)

from .dashboard import (
    dashboard,
    edit_meter,
)

from .export import export_meters_excel

from .termination import (
    termination_search,
    termination_detail,
    termination_toggle_installment,
)
from .download import download_form, download_excel

from .meter_master import meter_list, meter_form

__all__ = [
    'step1_upload', 'edit_staged_row', 'step2_review', 'step3_confirm',
    'step4_done', 'restart',
    'dashboard', 'edit_meter',
    'export_meters_excel',
    'termination_search', 'termination_detail', 'termination_toggle_installment',
    'download_form', 'download_excel',
    'meter_list', 'meter_form',
]