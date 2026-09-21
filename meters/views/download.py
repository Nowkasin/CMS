# meters/views/download.py
import datetime
import io
from urllib.parse import quote

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
    'ลำดับพื้นที่ย่อย', 'Location_id', 'สถานที่ตั้ง', 'Area_id',
    'พื้นที่ตามที่ตั้งพื้นที่เช่า', 'SubArea_id', 'พื้นที่ย่อยตามที่ตั้งพื้นที่เช่า', 'สถานะสัญญา',
    'ยืนยันพื้นที่ที่คิดค่าไฟ โดยใส่ 1 = มี, 0 = ไม่มี', 'ประเภทค่าใช้จ่าย',
    'ลำดับมิเตอร์EE_seq หากมี > 1เลข ให้ใส่เลขลำดับ เช่น 1, 2, 3…', 'เลขประจำเครื่องวัดไฟฟ้า',
    'กรอกระบบไฟฟ้า 2 ประเภท คือ ระบบไฟฟ้า 1 เฟส, ระบบไฟฟ้า 3 เฟส',
    'เลขที่อ่านครั้งหลัง', 'เลขที่อ่านครั้งก่อน', 'วันที่อ่านเลขมิเตอร์ไฟฟ้า', 'จำนวนเงินที่ต้องชำระ',
    'Document Date', 'Posting Date',
    'Document Type ส่วนพัฒนากายภาพ = DR, ส่วนพัฒนาความยั่งยืน = 61',
    'Base Line Date', 'วันที่ Upload ข้อมูล', 'ผู้Uploadข้อมูล', 'หมายเหตุ',
]


def _combined_key(r):
    """
    key รวมสำหรับ merge แถวน้ำ+ไฟที่เป็นสัญญา/พื้นที่ย่อยเดียวกันให้อยู่แถวเดียวกันในหน้าจอ
    (Contract_id + SubArea_id เท่านั้น -- ไม่รวม Meter_id เพราะต้องการรวมน้ำ+ไฟของพื้นที่ย่อย
    เดียวกันเข้าด้วยกัน ไม่ใช่แยกตามมิเตอร์เหมือน row_key เดิม)
    """
    return f"{r['Contract_id']}|{r['SubArea_id']}"


def _merge_water_electric(water_rows, electric_rows):
    """
    รวมแถวน้ำ+ไฟที่เป็นสัญญา/พื้นที่ย่อยเดียวกันเข้าด้วยกัน เพื่อโชว์เป็นแถวเดียวในหน้าจอเลือก
    (เหมือนการ์ดรวมน้ำ-ไฟใน edit_meter.html) -- แต่ตอน export Excel ยังคงแยก 2 ชีทเหมือนเดิม
    """
    combined = {}

    for r in water_rows:
        key = _combined_key(r)
        entry = combined.setdefault(key, {
            'row_key': key,
            'Contract_code': r.get('Contract_code'),
            'CompanyName': r.get('CompanyName'),
            'SubArea_id': r.get('SubArea_id'),
            'water': None,
            'electric': None,
        })
        entry['water'] = r

    for r in electric_rows:
        key = _combined_key(r)
        entry = combined.setdefault(key, {
            'row_key': key,
            'Contract_code': r.get('Contract_code'),
            'CompanyName': r.get('CompanyName'),
            'SubArea_id': r.get('SubArea_id'),
            'water': None,
            'electric': None,
        })
        entry['electric'] = r

    return sorted(
        combined.values(),
        key=lambda x: (x['Contract_code'] or '', x['SubArea_id'] or ''),
    )


def _dedupe_meter_rows(rows):
    """
    ตัดแถวซ้ำก่อนเขียนลง Excel -- query จาก services.fetch_contracts_for_download บางครั้งคืน
    แถวซ้ำสำหรับมิเตอร์เดียวกัน (ข้อมูลที่จะแสดงในไฟล์เหมือนกันทุกอย่าง) เข้าใจว่าเกิดจาก JOIN
    บางจุดใน services/download.py ที่ fan-out ซ้ำ ควรตามไปแก้ที่ต้นตอใน SQL query ด้วย

    ตั้งใจ dedupe ด้วยค่าที่ "แสดงผลจริง" ในไฟล์ (Meter_no ที่โชว์ + เลขอ่าน/จำนวนเงิน) แทนที่จะ
    ใช้ Meter_id ภายใน เพราะพบว่าบางครั้งแถวซ้ำมี Meter_id คนละค่ากัน (2 เรคคอร์ดในฐานข้อมูลที่ชี้
    ไปมิเตอร์คนละตัวแต่ Meter_no ที่แสดงเหมือนกัน) -- dedupe แบบเดิมที่ใช้ Meter_id จึงจับไม่ได้
    """
    seen = set()
    result = []
    for r in rows:
        key = (
            r['Contract_id'],
            r['SubArea_id'],
            r.get('Meter_no'),
            r.get('Contract_read_number_before'),
            r.get('Contract_read_number_after'),
            r.get('Contract_effective_date'),
            r.get('Contract_Installment_amt'),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(r)
    return result


def _seq_by_contract(rows):
    """นับลำดับมิเตอร์ 1,2,3... ต่อสัญญาเดียวกัน (สมมติฐานชั่วคราว -- ไม่มีคอลัมน์จริงให้ใช้)"""
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
            r['Contract_year'], r['Customer_id'], r['CompanyName'], r['TaxNumber'],
            r['Contract_id'], r['Contract_code'], r['Contract_Location_seq'], r['Location_name'],
            r['Area_id'], r['Area_name'], r['SubArea_id'], r['Contract_area_desc'],
            r['Status_contract_Desc'], 1, 'ค่าน้ำประปา', seq, r['Meter_no'],
            r['Contract_read_number_after'], r['Contract_read_number_before'],
            r['Contract_effective_date'], r['Contract_Installment_amt'],
            None, None, 'DR', r['Contract_duedate'], None, None, None,
        ])


def _write_electric_sheet(ws, rows):
    ws.append(ELECTRIC_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    seqs = _seq_by_contract(rows)
    for r, seq in zip(rows, seqs):
        ws.append([
            r['Contract_year'], r['Customer_id'], r['CompanyName'], r['TaxNumber'],
            r['Contract_id'], r['Contract_code'], r['Contract_Location_seq'], r['Location_id'],
            r['Location_name'], r['Area_id'], r['Area_name'], r['SubArea_id'],
            r['Contract_area_desc'], r['Status_contract_Desc'], 1, 'ค่าไฟฟ้า', seq,
            r['Meter_no'], r['Phase_type'], r['Contract_read_number_after'],
            r['Contract_read_number_before'], r['Contract_effective_date'],
            r['Contract_Installment_amt'], None, None, 'DR', r['Contract_duedate'],
            None, None, None,
        ])


def download_form(request):
    """
    หน้าเลือกเดือน-ปี + ค้นหา -- GET ธรรมดา (ไม่มี month/year) โชว์แค่ฟอร์มเปล่า
    ถ้ามี ?month=&year= (กดปุ่ม "ค้นหา") จะ query ข้อมูลจริงมาโชว์เป็นตารางเดียวที่รวมน้ำ+ไฟ
    ต่อสัญญา/พื้นที่ย่อยในหน้าเดียวกันเลย (เหมือนการ์ดรวมใน edit_meter.html) พร้อม checkbox
    ให้ติ๊กเลือกก่อนค่อยกดดาวน์โหลด Excel จริง (submit ไป download_excel แยกต่างหาก)
    """
    context = {
        'thai_months': THAI_MONTHS,
        'billing_month': datetime.date.today().month,
        'billing_year': _current_year_be(),
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
        'searched': False,
    }

    if 'month' in request.GET or 'year' in request.GET:
        errors = []
        year_be = _safe_int(request.GET.get('year'), 'ปี', errors) or _current_year_be()
        month = _safe_int(request.GET.get('month'), 'เดือน', errors) or datetime.date.today().month

        water_rows = _dedupe_meter_rows(services.fetch_contracts_for_download(9, year_be, month))
        electric_rows = _dedupe_meter_rows(services.fetch_contracts_for_download(8, year_be, month))

        combined_rows = _merge_water_electric(water_rows, electric_rows)

        context.update({
            'searched': True,
            'billing_month': month,
            'billing_year': year_be,
            'combined_rows': combined_rows,
        })

    return render(request, 'meters/download_form.html', context)


def download_excel(request):
    """
    สร้างไฟล์ Excel จากแถวที่ผู้ใช้ติ๊กเลือกในหน้าเว็บเท่านั้น (POST) -- query ข้อมูลเต็มใหม่อีกรอบ
    ด้วย month/year เดิม แล้วกรองเอาเฉพาะแถวที่ key รวม (Contract_id|SubArea_id) ตรงกับที่ติ๊กมา
    (ไม่เชื่อข้อมูลที่ POST มาตรงๆ เพราะ client ส่งอะไรมาก็ได้ -- query ใหม่จาก DB เสมอ ปลอดภัยกว่า)

    หน้าจอเลือกข้อมูลรวมน้ำ+ไฟเป็นแถวเดียว แต่ไฟล์ Excel ที่ export ออกมายังคงแยก 2 ชีท
    (น้ำ/ไฟ) เหมือนเดิม เพราะโครงสร้างคอลัมน์ตั้งต้นของแต่ละประเภทไม่เหมือนกัน
    """
    errors = []
    year_be = _safe_int(request.POST.get('year'), 'ปี', errors) or _current_year_be()
    month = _safe_int(request.POST.get('month'), 'เดือน', errors) or datetime.date.today().month

    selected_keys = set(request.POST.getlist('selected_rows'))

    water_rows = _dedupe_meter_rows([
        r for r in services.fetch_contracts_for_download(9, year_be, month)
        if _combined_key(r) in selected_keys
    ])
    electric_rows = _dedupe_meter_rows([
        r for r in services.fetch_contracts_for_download(8, year_be, month)
        if _combined_key(r) in selected_keys
    ])

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
    # ชื่อไฟล์มีอักขระไทย -- HTTP header ต้องเป็น ASCII เท่านั้น ถ้าใส่ภาษาไทยดิบๆ ลงไป
    # เบราว์เซอร์บางตัว (เช่น Chrome) จะอ่าน header ไม่ออกแล้ว fallback ไปใช้ชื่อ default
    # ("ดาวน์โหลด.xlsx" ตาม locale) แทน จึงต้อง encode ตาม RFC 5987 (filename*=UTF-8''...)
    # ควบคู่กับ filename="..." แบบ ASCII fallback (เผื่อเบราว์เซอร์เก่าที่ไม่รองรับ filename*)
    ascii_fallback = f"download_{month:02d}-{year_be}.xlsx"
    encoded_filename = quote(filename)
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )
    return response