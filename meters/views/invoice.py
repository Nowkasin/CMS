# meters/views/invoice.py
"""
ใบแจ้งหนี้ -- แทนฟอร์ม K2 FRM_4019_Invoice_CMS (สิทธิ์เมนู invoice_print)

หนึ่งใบแจ้งหนี้ = หนึ่งสัญญา + หนึ่งวันที่ตั้งหนี้ SAP รวมทุกเลขเอกสาร SAP ของวันนั้น (แบบร่าง V1.3)
invoice_search -- ค้นหาใบแจ้งหนี้ (GET) ช่องค้นหาเดียว เปิดมาเห็นเดือนที่ตั้งหนี้ล่าสุด หนึ่งแถวต่อหนึ่งใบ
invoice_print  -- หน้าใบแจ้งหนี้ขนาด A4 ทีละใบ (GET ?doc=<Contract_id>:<YYYYMMDD> หรือ
                  <Contract_id>:N<fi_doc> สำหรับงวดเก่าที่ไม่มีวันที่ตั้งหนี้) ผู้ใช้สั่งพิมพ์
                  หรือบันทึกเป็น PDF จากเบราว์เซอร์ ไม่สร้างไฟล์ PDF ฝั่งเซิร์ฟเวอร์
ทั้งสองหน้าอ่านข้อมูลอย่างเดียว การพิมพ์ถูกลงประวัติที่ log_middleware (REGISTRY: invoice_print)
"""
import datetime
import logging
import re
from urllib.parse import urlencode

from django.shortcuts import redirect, render

from ..services import invoice as invoice_service
from ..utils import baht_text, parse_iso_date, period_label, thai_date

logger = logging.getLogger(__name__)

UNIVERSITY_NAME = 'มหาวิทยาลัยศรีนครินทรวิโรฒ'
PERIOD_RE = re.compile(r'^\d{6}$')
# <Contract_id>:<YYYYMMDD> หรือ <Contract_id>:N<เลขเอกสาร SAP> (งวดที่ไม่มีวันที่ตั้งหนี้)
DOC_KEY_RE = re.compile(r'^(\d{1,10}):(?:(\d{8})|N([0-9A-Za-z/_-]{1,60}))$')


def _search_params(request):
    """
    อ่านและตรวจตัวกรองจาก query string -- คืน (params, errors)

    period: '' = ไม่ได้เลือก (ใช้เดือนล่าสุด), 'all' = ทุกเดือน, หรือ YYYYMM (ค.ศ.) ของวันที่ตั้งหนี้
    """
    get = request.GET
    errors = []
    params = {
        'q': get.get('q', '').strip()[:100],
        'period': get.get('period', '').strip(),
        'contract_year': get.get('year', '').strip(),
        'start_from_raw': get.get('start_from', '').strip(),
        'end_to_raw': get.get('end_to', '').strip(),
        'location': get.get('location', '').strip(),
    }
    if params['period'] not in ('', 'all'):
        if not PERIOD_RE.match(params['period']) or not 1 <= int(params['period'][4:]) <= 12:
            errors.append('เดือนที่ตั้งหนี้ไม่ถูกต้อง -- กรุณาเลือกเดือนจากรายการ')
            params['period'] = ''
    params['start_from'] = parse_iso_date(params['start_from_raw'])
    params['end_to'] = parse_iso_date(params['end_to_raw'])
    if params['start_from_raw'] and not params['start_from']:
        errors.append('วันที่เริ่มสัญญาไม่ถูกต้อง')
    if params['end_to_raw'] and not params['end_to']:
        errors.append('วันที่สิ้นสุดไม่ถูกต้อง')
    params['has_advanced'] = bool(params['contract_year'] or params['start_from_raw']
                                  or params['end_to_raw'] or params['location'])
    return params, errors


def doc_key(contract_id, fi_date, fi_doc):
    """คีย์ของใบแจ้งหนี้ใน ?doc= -- ดู DOC_KEY_RE"""
    if fi_date:
        return f'{contract_id}:{fi_date:%Y%m%d}'
    return f'{contract_id}:N{fi_doc}'


def group_invoices(rows):
    """
    บรรทัด -> ใบแจ้งหนี้ (สัญญา + วันที่ตั้งหนี้) เรียงตามลำดับที่ query คืนมา
    ผู้ใช้หาและพิมพ์ทีละใบ จึงแสดงหนึ่งแถวต่อหนึ่งใบพร้อมเลขเอกสารทุกเลขและยอดรวม
    """
    invoices = {}
    for row in rows:
        key = doc_key(row['Contract_id'], row.get('Contract_fi_date'), row['Contract_fi_doc'])
        inv = invoices.get(key)
        if inv is None:
            inv = invoices[key] = {
                'doc_key': key,
                'docs': [],
                'fi_date_label': thai_date(row.get('Contract_fi_date')),
                'contract_id': row['Contract_id'],
                'contract_code': row.get('Contract_code'),
                'company': row.get('CompanyName'),
                'customer_id': row.get('SAPVendor_Id'),
                'location': row.get('Contract_swu_location_name'),
                'owner': row.get('Contract_owner'),
                'sap_posted': True,
                'items': [],
                'periods': [],
                'total': 0,
            }
        if row['Contract_fi_doc'] not in inv['docs']:
            inv['docs'].append(row['Contract_fi_doc'])
        if str(row.get('Contract_debt_to_SAP') or '').strip() != '1':
            inv['sap_posted'] = False
        label = period_label(row.get('Period')) or row.get('Period')
        if label and label not in inv['periods']:
            inv['periods'].append(label)
        inv['items'].append({
            'desc': row.get('Contract_type_price_desc'),
            'doc': row['Contract_fi_doc'],
            'meter_no': row.get('Meter_no'),
            'meeting': row.get('Contract_meeting_adj'),
            'amount': row.get('Amount') or 0,
        })
        inv['total'] += row.get('Amount') or 0
    return list(invoices.values())


def invoice_search(request):
    params, errors = _search_params(request)
    load_error = None

    try:
        periods = invoice_service.fetch_invoice_periods()
        years = invoice_service.fetch_invoice_years()
        locations = invoice_service.fetch_invoice_locations()
    except Exception:
        logger.exception('invoice filter options failed')
        periods, years, locations = [], [], []
        load_error = 'โหลดข้อมูลไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง'

    # เปิดหน้ามา (ยังไม่ได้เลือกเดือน) = เดือนที่ตั้งหนี้ล่าสุด -- เห็นข้อมูลทันทีโดยไม่ต้องกรอกอะไร
    # ยกเว้นค้นด้วยคำค้น: ผู้ใช้ที่พิมพ์ชื่อ/เลขเอกสารมักไม่รู้เดือน จึงค้นทุกเดือนให้
    active_period = params['period']
    if active_period == '':
        active_period = 'all' if params['q'] else (periods[0] if periods else 'all')
    period_filter = '' if active_period == 'all' else active_period

    invoices, truncated, other_periods_count = [], False, 0
    if not load_error and not errors:
        filters = {
            'query': params['q'], 'contract_year': params['contract_year'],
            'start_from': params['start_from'], 'end_to': params['end_to'], 'location': params['location'],
        }
        try:
            rows, truncated = invoice_service.search_invoices(period=period_filter, **filters)
            invoices = group_invoices(rows)
            # ไม่เจอในเดือนที่เลือก -- ลองทุกเดือนเพื่อบอกทางไป แทนที่จะจบที่ "ไม่พบข้อมูล"
            if not invoices and period_filter and (params['q'] or params['has_advanced']):
                other_rows, _ = invoice_service.search_invoices(period='', **filters)
                other_periods_count = len(group_invoices(other_rows))
        except Exception:
            logger.exception('search_invoices failed')
            load_error = 'ค้นหาไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล กรุณาลองใหม่อีกครั้ง'

    period_options = [{'value': p, 'label': period_label(p) or p} for p in periods]
    quick_periods = []
    if periods:
        quick_periods.append({'value': periods[0], 'label': 'เดือนล่าสุด'})
    if len(periods) > 1:
        quick_periods.append({'value': periods[1], 'label': 'เดือนก่อน'})
    quick_periods.append({'value': 'all', 'label': 'ทุกเดือน'})

    return render(request, 'meters/invoice_search.html', {
        'params': params,
        'errors': errors,
        'load_error': load_error,
        'invoices': invoices,
        'invoice_total': sum(inv['total'] for inv in invoices),
        'truncated': truncated,
        'other_periods_count': other_periods_count,
        'active_period': active_period,
        'active_period_label': 'ทุกเดือน' if active_period == 'all' else (period_label(active_period) or active_period),
        'period_options': period_options,
        'quick_periods': quick_periods,
        'years': years,
        'locations': locations,
        'max_print': invoice_service.MAX_PRINT_DOCUMENTS,
        # query string ของคำค้น+ตัวกรองเพิ่มเติม (ไม่รวมเดือน) -- ปุ่มลัดเดือนต่อท้ายด้วย &period=
        'filter_qs': urlencode({k: v for k, v in (
            ('q', params['q']), ('year', params['contract_year']), ('start_from', params['start_from_raw']),
            ('end_to', params['end_to_raw']), ('location', params['location']),
        ) if v}),
    })


def parse_doc_keys(values):
    """
    ?doc= หลายค่า -> [(contract_id, fi_date หรือ None, fi_doc หรือ None)] ไม่ซ้ำ ตามลำดับเดิม
    ตัดค่าที่รูปแบบผิดหรือวันที่ไม่มีจริงทิ้ง
    """
    keys = []
    for value in values:
        match = DOC_KEY_RE.match((value or '').strip())
        if not match:
            continue
        contract_id, date_text, fi_doc = match.groups()
        fi_date = None
        if date_text:
            try:
                fi_date = datetime.datetime.strptime(date_text, '%Y%m%d').date()
            except ValueError:
                continue
        key = (contract_id, fi_date, None if fi_date else fi_doc)
        if key not in keys:
            keys.append(key)
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
        # บางสัญญาเก็บสถานที่เป็นชื่อเต็ม ("มหาวิทยาลัยศรีนครินทรวิโรฒ ประสานมิตร") -- ไม่ต่อชื่อซ้ำ
        location = (doc['header'].get('Contract_swu_location_name') or '').strip()
        doc['university_line'] = location if location.startswith(UNIVERSITY_NAME) \
            else f'{UNIVERSITY_NAME} {location}'.strip()
        doc['date_label'] = thai_date(doc['fi_date'])
        doc['total_text'] = baht_text(doc['total'])
        for line in doc['lines']:
            line['period_label'] = period_label(line.get('Period')) or line.get('Period')
            line['description'] = (line.get('Doc Header Text')
                                   or (line.get('Contract_type_price_desc') or '').strip())
    # ใช้ใน log_middleware -- บันทึกเลขเอกสาร SAP ที่พิมพ์ (ใบหนึ่งมีได้หลายเลข)
    request.activity_result = {
        'invoice_docs': [d for doc in documents for d in doc['docs']],
        'invoice_count': len(documents),
    }

    return render(request, 'meters/invoice_print.html', {
        'documents': documents,
        'missing_count': len(keys) - len(documents),
        'recorder': request.session.get('cms_display_name') or request.user.get_username(),
        'load_error': None,
    })
