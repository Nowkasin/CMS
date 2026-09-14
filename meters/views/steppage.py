# meters/views/wizard.py
import datetime

from django.shortcuts import render, redirect
from django.urls import reverse
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


def edit_staged_row(request, idx):
    """
    แก้ไข 1 แถวใน session['staged']['rows'] ก่อนกดยืนยันใน step 3
    (ใช้กับหน้า create_contract.html ที่จริงๆ คือหน้า "แก้ไข record ที่ parse มาแล้ว"
    ไม่ใช่หน้าสร้างสัญญาใหม่ -- ไม่มี SP/table เพิ่ม แก้ข้อมูลใน session ตรงๆ)
    """
    staged = request.session.get('staged')
    if not staged:
        return redirect('step1')

    rows = staged['rows']
    row = next((r for r in rows if r['idx'] == idx), None)
    if row is None:
        return redirect('step2')

    next_qs = request.GET.get('next', '') or request.POST.get('next', '')

    if request.method == 'POST':
        row['contract_code'] = request.POST.get('contract_code', '').strip() or None
        row['location_id'] = request.POST.get('location_id', '').strip()
        row['area_id'] = request.POST.get('area_id', '').strip()
        row['subarea_id'] = request.POST.get('subarea_id', '').strip()
        meter_no = request.POST.get('meter_no', '').strip()
        row['meter_no'] = meter_no or None

        if row['type_cd'] == 8:
            row['phase_type'] = request.POST.get('phase_type') or None

        # ตรวจสอบใหม่หลังแก้ไข (logic เดียวกับตอน parse ครั้งแรก)
        if not row['contract_code']:
            row['status'] = 'error'
            row['message'] = 'ไม่พบรหัสสัญญาในแถวนี้'
        elif not services.find_subarea(row['location_id'], row['area_id'], row['subarea_id']):
            row['status'] = 'error'
            row['message'] = f"ไม่พบพื้นที่ {row['location_id']}/{row['area_id']}/{row['subarea_id']} ในฐานข้อมูล"
        else:
            row['status'] = 'ok'
            row['message'] = ''
            row['meter_no_status'] = 'รอ Gen เลข' if not row['meter_no'] else 'ปกติ'

        # คำนวณสรุปยอดใหม่ทั้งชุด (จำนวน error/skip อาจเปลี่ยนหลังแก้)
        staged['summary'] = {
            'total': len(rows),
            'ok': sum(1 for r in rows if r['status'] == 'ok'),
            'skip': sum(1 for r in rows if r['status'] == 'skip'),
            'error': sum(1 for r in rows if r['status'] == 'error'),
        }
        request.session['staged'] = staged
        request.session.modified = True

        target = f"{reverse('step2')}?{next_qs}" if next_qs else reverse('step2')
        return redirect(target)

    context = {
        'current_step': 2, 'step_labels': STEP_LABELS,
        'row': row, 'next_qs': next_qs,
    }
    return render(request, 'meters/edit_row.html', context)


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