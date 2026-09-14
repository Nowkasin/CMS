# meters/views/download.py
import datetime
import io

from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook
from openpyxl.styles import Font

from .. import services
from .dashboard import THAI_MONTHS, _current_year_be, _safe_int

WATER_HEADERS = [
    'ปีที่สร้างสัญญา', 'รหัสลูกหนี้', 'ชื่อลูกหนี้', 'เลข13หลัก', 'เลขที่สัญญา', 'รหัสสัญญา',
    'ลำดับพื้นที่ย่อย', 'สถานที่ตั้ง', 'Area_id', 'พื้นที่ตามที่ตั้งพื้นที่เช่า', 'SubArea_id',
    'พื้นที่ย่อยตามที่ตั้งพื้นที่เช่า', 'สถานะสัญญา',
    'ยืนยันพื้นที่ที่คิดค่าน้ำ โดยใส่ 1 = มี, 0 = ไม่มี', 'ประเภทค่าใช้จ่าย',
    'ลำดับมิเตอร์WW_seq หากมี > 1เลข ให้ใส่เลขลำดับ เช่น 1, 2, 3…', 'เลขประจำเครื่องวัดน้ำประปา',
    'เลขที่อ่านครั้งหลัง', 'เลขที่อ่านครั้งก่อน', 'วันที่อ่านเลขมิเตอร์น้ำ', 'จำนวนเงินที่ต้องชำระ',
    'Document Date', 'Posting Date',
    'Document Type ส่วนพัฒนากายภาพ = DR, ส่วนพัฒนาความยั่งยืน = 61',
    'Base Line Date', 'วันที่ Upload ข้อมูล', 'ผู้Uploadข้อมูล', 'หมายเหตุ',
]

ELECTRIC_HEADERS = [
    'ปีที่สร้างสัญญา', 'รหัสลูกหนี้', 'ชื่อลูกหนี้', 'เลข13หลัก', 'เลขที่สัญญา', 'รหัสสัญญา',
    'Contract_grouping', 'ลำดับพื้นที่ย่อย', 'Location_id', 'สถานที่ตั้ง', 'Area_id',
    'พื้นที่ตามที่ตั้งพื้นที่เช่า', 'SubArea_id', 'พื้นที่ย่อยตามที่ตั้งพื้นที่เช่า', 'ประเภทสัญญา',
    'สถานะสัญญา', 'ยืนยันพื้นที่ที่คิดค่าไฟ โดยใส่ 1 = มี, 0 = ไม่มี', 'ประเภทค่าใช้จ่าย',
    'ลำดับมิเตอร์EE_seq หากมี > 1เลข ให้ใส่เลขลำดับ เช่น 1, 2, 3…', 'เลขประจำเครื่องวัดไฟฟ้า',
    'กรอกระบบไฟฟ้า 2 ประเภท คือ ระบบไฟฟ้า 1 เฟส, ระบบไฟฟ้า 3 เฟส',
    'เลขที่อ่านครั้งหลัง', 'เลขที่อ่านครั้งก่อน', 'วันที่อ่านเลขมิเตอร์ไฟฟ้า', 'จำนวนเงินที่ต้องชำระ',
    'Document Date', 'Posting Date',
    'Document Type ส่วนพัฒนากายภาพ = DR, ส่วนพัฒนาความยั่งยืน = 61',
    'Base Line Date', 'วันที่ Upload ข้อมูล', 'ผู้Uploadข้อมูล', 'หมายเหตุ',
]


def _seq_by_contract(rows):
    """นับลำดับมิเตอร์ 1,2,3... ต่อสัญญาเดียวกัน (สมมติฐานชั่วคราว ดู docstring ใน services/download.py)"""
    counters = {}
    result = []
    for r in rows:
        counters[r['Contract_id']] = counters.get(r['Contract_id'], 0) + 1
        result.append(counters[r['Contract_id']])
    return result


def _write_water_sheet(ws, rows):
    ws.append(WATER_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    seqs = _seq_by_contract(rows)
    for r, seq in zip(rows, seqs):
        ws.append([
            r['Contract_year'],
            r['Customer_id'],
            r['CompanyName'],
            r['TaxNumber'],
            r['Contract_id'],
            r['Contract_code'],
            seq,
            r['Location_name'],
            r['Area_id'],
            r['Area_name'],
            r['SubArea_id'],
            r['SubArea_name'],
            'สัญญา',
            1,
            'ค่าน้ำประปา',
            seq,
            r['Meter_no'],
            r['Contract_read_number_after'],
            r['Contract_read_number_before'],
            r['Contract_effective_date'],
            r['Contract_Installment_amt'],
            None, None, 'DR', None, None, None, None,
        ])


def _write_electric_sheet(ws, rows):
    ws.append(ELECTRIC_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    seqs = _seq_by_contract(rows)
    for r, seq in zip(rows, seqs):
        ws.append([
            r['Contract_year'],
            r['Customer_id'],
            r['CompanyName'],
            r['TaxNumber'],
            r['Contract_id'],
            r['Contract_code'],
            r['Contract_grouping'],
            seq,
            r['Location_id'],
            r['Location_name'],
            r['Area_id'],
            r['Area_name'],
            r['SubArea_id'],
            r['SubArea_name'],
            'สัญญาเช่า',
            'สัญญา',
            1,
            'ค่าไฟฟ้า',
            seq,
            r['Meter_no'],
            r['Phase_type'],
            r['Contract_read_number_after'],
            r['Contract_read_number_before'],
            r['Contract_effective_date'],
            r['Contract_Installment_amt'],
            None, None, 'DR', None, None, None, None,
        ])


def download_form(request):
    """
    หน้าเลือกเดือน-ปี ก่อนดาวน์โหลด Excel -- แค่แสดงฟอร์ม ไม่ดึงข้อมูลอะไรในนี้
    กดปุ่มแล้วจะ GET ไปที่ download_excel (URL คนละตัว) เพื่อสร้างไฟล์จริง
    """
    context = {
        'thai_months': THAI_MONTHS,
        'billing_month': datetime.date.today().month,
        'billing_year': _current_year_be(),
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
    }
    return render(request, 'meters/download_form.html', context)


def download_excel(request):
    """
    สร้างไฟล์ Excel (2 ชีต: น้ำประปา, ไฟฟ้า) ตามเดือน-ปีที่เลือก แล้วส่งกลับเป็น attachment
    ให้ browser ดาวน์โหลดทันที (ไม่ผ่านหน้า render ใดๆ)
    """
    errors = []
    year_be = _safe_int(request.GET.get('year'), 'ปี', errors) or _current_year_be()
    month = _safe_int(request.GET.get('month'), 'เดือน', errors) or datetime.date.today().month

    water_rows = services.fetch_contracts_for_download(9, year_be, month)
    electric_rows = services.fetch_contracts_for_download(8, year_be, month)

    wb = Workbook()
    ws1 = wb.active
    ws1.title = f"สัญญาปี{year_be}_น้ำประปา"[:31]
    _write_water_sheet(ws1, water_rows)

    ws2 = wb.create_sheet(title=f"สัญญาปี{year_be}_ไฟฟ้า"[:31])
    _write_electric_sheet(ws2, electric_rows)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"สัญญาน้ำ-ไฟ_{month:02d}-{year_be}.xlsx"
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response