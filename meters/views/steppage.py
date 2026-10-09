# meters/views/wizard.py
import datetime

from django.conf import settings
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

            # parse_excel_staged โยน ValueError พร้อมข้อความไทยที่เขียนไว้ให้ผู้ใช้อ่าน
            # 2 จุด (ชีทชื่อซ้ำเกิน 1 / หาคอลัมน์ header ไม่เจอ) เดิมไม่มีใครรับ
            # ผู้ใช้จึงเห็นหน้า 500 แทนคำแนะนำที่เขียนไว้แล้ว
            #
            # ใส่เป็น error ของ field ด้วย form.add_error -- เทมเพลตแสดง
            # form.excel_file.errors.0 อยู่แล้ว ไม่ต้องแก้หน้าจอ
            parsed = None
            try:
                parsed = services.parse_excel_staged(excel_file)
            except ValueError as exc:
                form.add_error('excel_file', str(exc))
            except Exception:
                # error อื่น (ไฟล์เสียกลางทาง, openpyxl อ่านไม่ออก) -- ไม่โชว์ข้อความดิบ
                form.add_error(
                    'excel_file',
                    'อ่านไฟล์ไม่สำเร็จ -- ไฟล์อาจเสียหายหรือไม่ใช่รูปแบบที่ระบบรองรับ '
                    'กรุณาตรวจสอบไฟล์แล้วลองใหม่',
                )

            if parsed is not None:
                max_rows = getattr(settings, 'EXCEL_UPLOAD_MAX_ROWS', 5000)
                row_count = len(parsed['rows'])
                if row_count > max_rows:
                    # ข้อมูล staged ถูกเก็บใน session -- ไฟล์ใหญ่มากจะทำให้ session
                    # ใหญ่ตามและหน้า review ช้า จึงกันไว้พร้อมบอกตัวเลขจริง
                    form.add_error(
                        'excel_file',
                        f'ไฟล์นี้มี {row_count:,} แถว เกินที่ระบบรับได้ ({max_rows:,} แถว) '
                        f'กรุณาแบ่งไฟล์ออกเป็นหลายไฟล์แล้วอัปโหลดทีละไฟล์',
                    )
                else:
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
        # ใช้ .get() ให้ตรงกับบรรทัดถัดไป -- เดิมเป็น r['type_cd'] ซึ่งถ้าคีย์หาย
        # (เช่น session ค้างจากโครงข้อมูลเวอร์ชันก่อน) จะเป็น KeyError -> หน้า 500
        filtered = [r for r in filtered if str(r.get('type_cd')) == type_filter]
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
            # commit_staged_rows ทำ rollback ให้แล้วถ้าพัง แต่เดิมไม่มีใครรับ exception
            # ผู้ใช้จึงเห็นหน้า 500 -- ข้อมูล staged ยังอยู่ใน session (ดี) แต่ไม่มี
            # อะไรบอกว่าเกิดอะไรขึ้นและควรทำอย่างไรต่อ
            try:
                # ส่งชื่อไฟล์/รอบบิลไปด้วยเพื่อเขียน Contract_activity_log
                # (สองค่านี้มีอยู่แค่ใน session ไม่มีใน DB)
                result = services.commit_staged_rows(
                    staged['rows'], DEFAULT_USER,
                    source_filename=staged.get('filename'),
                    billing_period=staged.get('billing_period'),
                )
            except Exception:
                # ไม่โชว์ข้อความดิบจาก pyodbc/SQL Server (มีชื่อตาราง/driver ติดมา)
                # คง staged ไว้ให้กดยืนยันซ้ำได้ ไม่ต้องอัปโหลดไฟล์ใหม่
                error = (
                    'บันทึกข้อมูลไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล '
                    'ข้อมูลที่ตรวจสอบไว้ยังอยู่ กรุณากดยืนยันอีกครั้ง '
                    'หากยังไม่สำเร็จกรุณาติดต่อผู้ดูแลระบบ'
                )
            else:
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