# meters/views/wizard.py
import datetime

from django.shortcuts import render, redirect
from django.core.paginator import Paginator

from .. import services
from ..forms import ExcelUploadForm

DEFAULT_USER = 'web_upload'
STEP_LABELS = ['อัปโหลดไฟล์', 'ตรวจสอบข้อมูล', 'ยืนยันนำเข้า', 'เสร็จสิ้น']

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


def _current_year_be():
    return datetime.date.today().year + 543


def _safe_month(raw, fallback):
    """
    แปลงเดือนที่ POST มาเป็น int 1-12 -- ถ้าไม่ใช่ตัวเลขหรืออยู่นอกช่วง คืน fallback
    (ไม่ throw และไม่ปล่อยให้เป็น index ติดลบที่จะได้เดือนผิดแบบเงียบๆ)
    """
    try:
        month = int(raw)
    except (TypeError, ValueError):
        return fallback
    return month if 1 <= month <= 12 else fallback


def _safe_year(raw, fallback):
    """
    แปลงปี พ.ศ. ที่ POST มาเป็น int -- ถ้าไม่ใช่ตัวเลขหรือดูไม่สมเหตุสมผล คืน fallback
    ช่วงที่ยอมรับ 2500-2700 กันค่าอย่าง 0 หรือปี ค.ศ. ที่กรอกผิดช่อง
    """
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return fallback
    return year if 2500 <= year <= 2700 else fallback


def _previous_month():
    """
    คืน (month_idx 1-12, year_be) ของเดือนก่อนหน้าปัจจุบัน -- ใช้เป็นค่า default ของรอบบิล
    ที่ดำเนินการในหน้า upload (ปกติจะบันทึกค่าน้ำ-ค่าไฟของเดือนที่ผ่านมา ไม่ใช่เดือนปัจจุบัน)
    เผื่อกรณีเดือนมกราคม (เดือน 1) เดือนก่อนหน้าคือธันวาคมของปีก่อน -- ต้องถอยปีด้วย
    """
    today = datetime.date.today()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    return last_month.month, last_month.year + 543


def step1_upload(request):
    prev_month_idx, prev_year_be = _previous_month()
    context = {
        'form': ExcelUploadForm(),
        'current_step': 1,
        'step_labels': STEP_LABELS,
        'thai_months': THAI_MONTHS,
        'current_month_idx': prev_month_idx,
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
        'current_year_be': prev_year_be,
    }

    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        context['form'] = form
        if form.is_valid():
            excel_file = form.cleaned_data['excel_file']
            # ต้อง validate ก่อนใช้เป็น index: ค่าที่ POST มาเชื่อถือไม่ได้
            # ถ้าใช้ int() ตรงๆ แล้วส่งค่าอย่าง 'abc' มาจะ ValueError -> 500
            # และ 0 / ค่าว่าง จะกลายเป็น THAI_MONTHS[-1] = 'ธันวาคม' แบบเงียบๆ (รอบบิลผิดโดยไม่รู้ตัว)
            prev_month_idx, prev_year_be = _previous_month()
            month_idx = _safe_month(request.POST.get('billing_month'), prev_month_idx)
            year_be = _safe_year(request.POST.get('billing_year'), prev_year_be)
            billing_period = f"{THAI_MONTHS[month_idx - 1]} {year_be}"

            parsed = services.parse_excel_staged(excel_file)

            request.session['staged'] = {
                'filename': excel_file.name,
                'billing_period': billing_period,
                'rows': parsed['rows'],
                'summary': parsed['summary'],
            }
            request.session.modified = True
            return redirect('step2')

    return render(request, 'meters/upload.html', context)


def step2_review(request):
    staged = request.session.get('staged')
    if not staged:
        return redirect('step1')

    rows = staged['rows']
    q = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type', 'all')

    filtered = rows
    if type_filter in ('8', '9'):
        filtered = [r for r in filtered if str(r['type_cd']) == type_filter]
    if q:
        ql = q.lower()
        filtered = [
            r for r in filtered
            if ql in (r.get('contract_code') or '').lower()
            or ql in (r.get('subarea_id') or '').lower()
            or ql in (r.get('meter_no') or '').lower()
        ]

    paginator = Paginator(filtered, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'current_step': 2, 'step_labels': STEP_LABELS,
        'staged': staged, 'page_obj': page_obj,
        'search': q, 'active_filter': type_filter,
        'total_filtered': len(filtered),
    }
    return render(request, 'meters/review.html', context)


def step3_confirm(request):
    staged = request.session.get('staged')
    if not staged:
        return redirect('step1')

    error = None
    if request.method == 'POST':
        if request.POST.get('confirm') != 'on':
            error = 'กรุณายืนยันว่าตรวจสอบข้อมูลถูกต้องและครบถ้วนแล้วก่อนบันทึก'
        else:
            result = services.commit_staged_rows(staged['rows'], DEFAULT_USER)
            request.session['committed'] = {
                'filename': staged['filename'],
                'billing_period': staged['billing_period'],
                'logs': result['logs'],
                'stats': result['stats'],
                'rows': result['rows'],
            }
            del request.session['staged']
            request.session.modified = True
            return redirect('step4')

    context = {
        'current_step': 3, 'step_labels': STEP_LABELS,
        'staged': staged, 'error': error,
    }
    return render(request, 'meters/confirm.html', context)


def step4_done(request):
    committed = request.session.get('committed')
    if not committed:
        return redirect('step1')

    context = {'current_step': 4, 'step_labels': STEP_LABELS, 'committed': committed}
    return render(request, 'meters/done.html', context)


def restart(request):
    request.session.pop('staged', None)
    request.session.pop('committed', None)
    return redirect('step1')