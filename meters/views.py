# meters/views.py
"""
4 step wizard:
  step1_upload  -> parse ไฟล์ เก็บใน session (session['staged']) -- ไม่เขียน DB
  step2_review  -> โชว์ตารางจาก session ตรวจทาน/ค้นหา/กรอง
  step3_confirm -> สรุปยอด + checkbox ยืนยัน -> POST ค่อยเขียน DB จริง (session['committed'])
  step4_done    -> โชว์ผลลัพธ์จริงหลังบันทึก
"""
import datetime

from django.shortcuts import render, redirect
from django.core.paginator import Paginator

from . import services
from .forms import ExcelUploadForm

DEFAULT_USER = 'web_upload'
STEP_LABELS = ['อัปโหลดไฟล์', 'ตรวจสอบข้อมูล', 'ยืนยันนำเข้า', 'เสร็จสิ้น']

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


def _current_year_be():
    return datetime.date.today().year + 543


def step1_upload(request):
    context = {
        'form': ExcelUploadForm(),
        'current_step': 1,
        'step_labels': STEP_LABELS,
        'thai_months': THAI_MONTHS,
        'current_month_idx': datetime.date.today().month,
        'year_options': [_current_year_be() - 1, _current_year_be(), _current_year_be() + 1],
        'current_year_be': _current_year_be(),
    }

    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        context['form'] = form
        if form.is_valid():
            excel_file = form.cleaned_data['excel_file']
            month_idx = int(request.POST.get('billing_month', datetime.date.today().month))
            year_be = int(request.POST.get('billing_year', _current_year_be()))
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


def dashboard(request):
    type_filter = request.GET.get('type', 'all')
    search = request.GET.get('q', '')
    context = {
        'stats': services.fetch_dashboard_stats(),
        'meters': services.fetch_meters(type_filter, search),
        'subareas': services.fetch_subareas(),
        'active_filter': type_filter,
        'search': search,
    }
    return render(request, 'meters/dashboard.html', context)

def create_contract(request):
    return render(request, 'meters/create_contract.html')