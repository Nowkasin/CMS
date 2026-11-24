# meters/views/invoice.py
"""
ใบแจ้งหนี้ -- แทนฟอร์ม K2 FRM_4019_Invoice_CMS (สิทธิ์เมนู invoice_print)

invoice_search -- ค้นหางวดที่ตั้งหนี้แล้ว (GET) ติ๊กเลือก แล้วกดพิมพ์
invoice_print  -- หน้าใบแจ้งหนี้ขนาด A4 ทีละใบ (GET ?doc=<Contract_id>:<fi_doc>) ผู้ใช้สั่งพิมพ์
                  หรือบันทึกเป็น PDF จากเบราว์เซอร์ ไม่สร้างไฟล์ PDF ฝั่งเซิร์ฟเวอร์
ทั้งสองหน้าอ่านข้อมูลอย่างเดียว การพิมพ์ถูกลงประวัติที่ log_middleware (REGISTRY: invoice_print)
"""
import logging
import re

from django.shortcuts import redirect, render

from ..services import invoice as invoice_service
from ..utils import baht_text, parse_iso_date, period_label, thai_date

logger = logging.getLogger(__name__)

PERIOD_RE = re.compile(r'^\d{6}$')
DOC_KEY_RE = re.compile(r'^(\d{1,10}):([0-9A-Za-z/_-]{1,60})$')


def _search_params(request):
    """อ่านและตรวจตัวกรองจาก query string -- คืน (params, errors)"""
    get = request.GET
    errors = []
    params = {
        'contract_year': get.get('year', '').strip(),
        'period': get.get('period', '').strip(),
        'contract_code': get.get('contract', '').strip(),
        'start_from_raw': get.get('start_from', '').strip(),
        'end_to_raw': get.get('end_to', '').strip(),
        'location': get.get('location', '').strip(),
        'name': get.get('name', '').strip(),
    }
    if params['period'] and not PERIOD_RE.match(params['period']):
        errors.append('ประจำงวดต้องเป็นตัวเลข 6 หลัก ปี ค.ศ. ตามด้วยเดือน เช่น 202611')
    elif params['period'] and not 1 <= int(params['period'][4:]) <= 12:
        errors.append('เดือนในประจำงวดต้องอยู่ระหว่าง 01-12')
    params['start_from'] = parse_iso_date(params['start_from_raw'])
    params['end_to'] = parse_iso_date(params['end_to_raw'])
    if params['start_from_raw'] and not params['start_from']:
        errors.append('วันที่เริ่มสัญญาไม่ถูกต้อง')
    if params['end_to_raw'] and not params['end_to']:
        errors.append('วันที่สิ้นสุดไม่ถูกต้อง')
    return params, errors


def invoice_search(request):
    params, errors = _search_params(request)
    searched = 'year' in request.GET
    if searched and not params['contract_year']:
        errors.append('กรุณาเลือกปีที่สร้างสัญญา')

    rows = []
    load_error = None
    if searched and not errors:
        try:
            rows = invoice_service.search_invoices(
                params['contract_year'], params['period'], params['contract_code'],
                params['start_from'], params['end_to'], params['location'], params['name'],
            )
        except Exception:
            logger.exception('search_invoices failed')
            load_error = 'ค้นหาไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง'

    for row in rows:
        row['doc_key'] = f"{row['Contract_id']}:{row['Contract_fi_doc']}"
        row['period_label'] = period_label(row.get('Contract_Installment_month_year'))
        row['duedate_label'] = thai_date(row.get('Contract_duedate'))
        row['fi_date_label'] = thai_date(row.get('Contract_fi_date'))
        row['sap_status'] = 'ตั้งหนี้' if str(row.get('Contract_debt_to_SAP') or '').strip() == '1' else 'ยังไม่ตั้งหนี้'

    try:
        years = invoice_service.fetch_invoice_years()
        locations = invoice_service.fetch_invoice_locations()
    except Exception:
        logger.exception('invoice filter options failed')
        years, locations = [], []
        load_error = load_error or 'โหลดตัวเลือกการค้นหาไม่สำเร็จ -- กรุณาลองใหม่อีกครั้ง'

    return render(request, 'meters/invoice_search.html', {
        'params': params,
        'errors': errors,
        'load_error': load_error,
        'searched': searched,
        'rows': rows,
        'years': years,
        'locations': locations,
        'max_print': invoice_service.MAX_PRINT_DOCUMENTS,
    })


def parse_doc_keys(values):
    """?doc=<Contract_id>:<fi_doc> หลายค่า -> [(contract_id, fi_doc)] ไม่ซ้ำ ตามลำดับเดิม ตัดค่าที่รูปแบบผิดทิ้ง"""
    keys = []
    for value in values:
        match = DOC_KEY_RE.match((value or '').strip())
        if match and (match.group(1), match.group(2)) not in keys:
            keys.append((match.group(1), match.group(2)))
    return keys


def invoice_print(request):
    keys = parse_doc_keys(request.GET.getlist('doc'))
    if not keys:
        return redirect('invoice_search')
    if len(keys) > invoice_service.MAX_PRINT_DOCUMENTS:
        keys = keys[:invoice_service.MAX_PRINT_DOCUMENTS]

    try:
        documents = invoice_service.fetch_invoice_documents(keys)
    except Exception:
        logger.exception('fetch_invoice_documents failed')
        return render(request, 'meters/invoice_print.html', {
            'documents': [],
            'load_error': 'ดึงข้อมูลใบแจ้งหนี้ไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง',
        })

    for doc in documents:
        header = doc['header']
        doc['invoice_no'] = f"{doc['fi_doc']} / {header.get('fiscal_year') or ''}".strip(' /')
        doc['date_label'] = header.get('Contract_fi_date_thai') or thai_date(header.get('Contract_fi_date'))
        doc['total_text'] = baht_text(doc['total'])
        for line in doc['lines']:
            line['period_label'] = period_label(line.get('Contract_Installment_month_year')) \
                or line.get('Contract_Installment_month_year')
            line['description'] = line.get('Doc Header Text') or line.get('Contract_type_price_desc')
    # ใช้ใน log_middleware -- บันทึกว่าพิมพ์ใบไหนบ้าง
    request.activity_result = {'invoice_docs': [doc['fi_doc'] for doc in documents]}

    return render(request, 'meters/invoice_print.html', {
        'documents': documents,
        'missing_count': len(keys) - len(documents),
        'recorder': request.session.get('cms_display_name') or request.user.get_username(),
        'load_error': None,
    })
