"""
เมนูค่าล้างจาน -- บันทึกยอดค่าล้างจานรายเดือนต่อสัญญา (ผู้ใช้กรอกยอดเอง)

GET  ?year=<พ.ศ.>&month=<1-12>&q=<คำค้น>  รายการสัญญาของรอบบิลนั้น พร้อมช่องกรอกยอด
POST บันทึกเฉพาะสัญญาที่แสดงอยู่บนหน้าตอนกด (hidden contract_ids) -- คำค้นที่กรองอยู่จึงไม่ทำให้
     ยอดของสัญญาที่ซ่อนอยู่ถูกลบ ล้างช่องยอด = ลบรายการของรอบนั้น
แถวที่ตั้งหนี้ SAP แล้วแก้ไม่ได้ (ช่องถูกล็อกบนหน้าจอ และ service ข้ามให้อีกชั้น)
บันทึกแล้วลง activity log ผ่าน log_middleware (view ฝากผลไว้ใน request.activity_result)
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse

from ..services import dishwash as service
from ..utils import THAI_MONTHS, current_year_be, safe_int, thai_datetime, year_options

logger = logging.getLogger(__name__)


def _parse_amount(raw, label, errors):
    """ยอดเงิน: ว่าง = None, ตัวเลขไม่ติดลบ ทศนิยมไม่เกิน 2 ตำแหน่ง ใส่จุลภาคคั่นหลักได้"""
    text = (raw or '').strip().replace(',', '')
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        errors.append(f"{label}: ยอดเงินต้องเป็นตัวเลข (พิมพ์มาว่า '{raw}')")
        return None
    if not value.is_finite() or value < 0:
        errors.append(f"{label}: ยอดเงินต้องไม่ติดลบ (พิมพ์มาว่า '{raw}')")
        return None
    if value != value.quantize(Decimal('0.01')):
        errors.append(f"{label}: ทศนิยมได้ไม่เกิน 2 ตำแหน่ง (พิมพ์มาว่า '{raw}')")
        return None
    if value > service.MAX_DISHWASH_AMOUNT:
        errors.append(f"{label}: ยอดเงินสูงเกินไป (พิมพ์มาว่า '{raw}')")
        return None
    return value.quantize(Decimal('0.01'))


def _period(request, errors):
    source = request.POST if request.method == 'POST' else request.GET
    year = safe_int(source.get('year'), 'ปี', errors, min_value=2400, max_value=2700)
    month = safe_int(source.get('month'), 'เดือน', errors, min_value=1, max_value=12)
    return (year or current_year_be(), month or datetime.date.today().month)


def dishwash(request):
    errors = []
    year_be, month = _period(request, errors)
    search = (request.POST.get('q') if request.method == 'POST' else request.GET.get('q')) or ''
    search = search.strip()
    posted = {}

    if request.method == 'POST' and not errors:
        contract_ids = []
        for raw in request.POST.getlist('contract_ids'):
            if str(raw).isdigit():
                contract_ids.append(int(raw))
        entries = []
        for contract_id in contract_ids:
            code = (request.POST.get(f'code_{contract_id}') or str(contract_id)).strip()
            amount_raw = request.POST.get(f'amount_{contract_id}', '')
            remark = (request.POST.get(f'remark_{contract_id}') or '').strip()
            posted[contract_id] = {'amount': amount_raw, 'remark': remark}
            amount = _parse_amount(amount_raw, f'สัญญา {code}', errors)
            if len(remark) > service.MAX_DISHWASH_REMARK_LEN:
                errors.append(f'สัญญา {code}: หมายเหตุยาวเกิน {service.MAX_DISHWASH_REMARK_LEN} ตัวอักษร')
            if amount is None and remark and amount_raw.strip() == '':
                errors.append(f'สัญญา {code}: กรอกหมายเหตุแล้วต้องกรอกยอดเงินด้วย')
            entries.append({'contract_id': contract_id, 'amount': amount, 'remark': remark})

        if not errors:
            try:
                result = service.save_dishwash_month(year_be, month, entries, request.user.get_username())
            except Exception:
                logger.exception('save_dishwash_month failed year=%s month=%s', year_be, month)
                errors.append('บันทึกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล ยังไม่มีข้อมูลใดถูกบันทึก '
                              'กรุณาลองใหม่อีกครั้ง')
            else:
                request.activity_result = {'dishwash': result, 'year_be': year_be, 'month': month}
                query = {'year': year_be, 'month': month, 'saved': '1',
                         'c': len(result['created']), 'u': len(result['updated']),
                         'd': len(result['deleted']), 'l': len(result['locked'])}
                if search:
                    query['q'] = search
                return redirect(f"{reverse('dishwash')}?{urlencode(query)}")

    rows = []
    try:
        rows = service.fetch_dishwash_month(year_be, month, search)
    except Exception:
        logger.exception('fetch_dishwash_month failed year=%s month=%s', year_be, month)
        errors.append('อ่านข้อมูลจากฐานข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')

    total = Decimal('0')
    for row in rows:
        row['locked'] = bool(row.get('Contract_fi_doc'))
        row['saved_label'] = thai_datetime(row.get('Saved_at')) if row.get('Saved_at') else ''
        if row.get('Amount') is not None:
            total += Decimal(row['Amount'])
        again = posted.get(row['Contract_id'])
        if again is not None:
            row['amount_input'], row['remark_input'] = again['amount'], again['remark']
        else:
            row['amount_input'] = f"{row['Amount']:.2f}" if row.get('Amount') is not None else ''
            row['remark_input'] = row.get('Remark') or ''

    saved = None
    if request.method == 'GET' and request.GET.get('saved') == '1':
        saved = {key: safe_int(request.GET.get(key), key, [], min_value=0) or 0 for key in ('c', 'u', 'd', 'l')}

    return render(request, 'meters/dishwash.html', {
        'rows': rows,
        'filled_count': sum(1 for r in rows if r.get('Amount') is not None),
        'total': total,
        'billing_year': year_be,
        'billing_month': month,
        'month_label': f'{THAI_MONTHS[month - 1]} {year_be}',
        'thai_months': THAI_MONTHS,
        'year_options': sorted(set(year_options() + [year_be])),
        'search': search,
        'errors': errors,
        'saved': saved,
    })
