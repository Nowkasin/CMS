import calendar
import logging
from datetime import date

from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .dashboard import THAI_MONTHS
from ..services.space_profile import load_space_period, save_space_details, get_period_navigation, SpaceProfileError, space_filter_options, filter_space_rows
from ..forms import SpacePeriodForm, SpaceDetailsForm, SpaceFilterForm


logger = logging.getLogger(__name__)


@require_http_methods(['GET', 'POST'])
def space_profile_preview(request, subarea_id=None):
    """รายการตรวจข้อมูลรายเดือน และหน้ารายละเอียดพื้นที่แยกจากรายการ"""
    today = timezone.localdate()
    permissions = request.session.get('cms_permissions', {})
    if not permissions.get('space_profile_view'):
        return render(request, 'meters/404.html', status=404)
    can_edit = True
    if request.method == 'POST':
        action = request.POST.get('action')
        if action != 'save':
            return render(request, 'meters/404.html', status=404)
    active_date = None
    closed_dates = []
    navigation_error = ''
    try:
        active_date, closed_dates = get_period_navigation()
    except Exception as exc:
        logger.error('Space periods query failed error_type=%s', type(exc).__name__)
        navigation_error = 'ไม่สามารถโหลดรอบข้อมูลได้ กรุณาลองใหม่'
    default_date = active_date or today
    month, year_be = default_date.month, default_date.year + 543
    period_error = ''
    params = request.POST if request.method == 'POST' else request.GET
    filter_params = {name: params.get(name, '') for name in ('business', 'location', 'area_status')}
    tab = 'history' if params.get('tab') == 'history' else 'work'
    if tab == 'history':
        requested = params.get('period', '')
        selected_date = next((d for d in closed_dates if d.isoformat() == requested), None)
        if not requested and closed_dates:
            selected_date = closed_dates[0]
        if selected_date:
            month, year_be = selected_date.month, selected_date.year + 543
        elif requested:
            period_error = 'ไม่พบรอบประวัติที่เลือก'
    period_form = SpacePeriodForm({'month': params.get('month', month) if tab == 'work' else month, 'year': params.get('year', year_be) if tab == 'work' else year_be})
    if period_form.is_valid():
        month, year_be = period_form.cleaned_data['month'], period_form.cleaned_data['year']
    else:
        period_error = 'กรุณาเลือกเดือนและปีที่ถูกต้อง'

    year = year_be - 543
    target_date = date(year, month, calendar.monthrange(year, month)[1])
    rows = []
    data_error = navigation_error
    closed = editable = False
    period_open = reopened = False
    action_error = ''
    details_form = None
    if request.method == 'POST' and not period_error and not data_error:
        try:
            action = request.POST.get('action')
            if tab == 'history' and action != 'reopen':
                raise SpaceProfileError('ประวัติรายเดือนเปิดดูได้อย่างเดียว')
            if action == 'save':
                if subarea_id is None:
                    raise SpaceProfileError('กรุณาเปิดพื้นที่ที่ต้องการแก้ไขจากรายการ')
                details_form = SpaceDetailsForm(request.POST)
                if details_form.is_valid():
                    save_space_details(target_date, subarea_id, details_form.as_details(), request.user.get_username())
                else:
                    raise SpaceProfileError('กรุณาตรวจสอบข้อมูลที่กรอกให้ครบและไม่เกินความยาวที่กำหนด')
            else:
                raise SpaceProfileError('ไม่พบการดำเนินการที่ระบุ')
            query = urlencode({'month': month, 'year': year_be, 'page': params.get('page', '1'), 'result': action, **filter_params})
            return redirect(f"{reverse('space_profile_preview')}?{query}")
        except SpaceProfileError as exc:
            action_error = str(exc)
        except Exception as exc:
            logger.error('Space profile write failed error_type=%s', type(exc).__name__)
            action_error = 'บันทึกไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'
    if not period_error and not data_error and (tab == 'work' or closed_dates):
        try:
            if tab == 'work' and target_date != active_date:
                raise SpaceProfileError('กรุณาจัดทำรอบปัจจุบันให้เสร็จก่อนเริ่มเดือนถัดไป')
            if tab == 'history' and target_date not in closed_dates:
                raise SpaceProfileError('ไม่พบรอบที่ปิดแล้ว')
            period = load_space_period(target_date)
            rows, closed, editable = period['rows'], period['closed'], period['editable']
            period_open = editable
            reopened = period.get('reopened', False)
            if tab == 'history':
                editable = False
            editable = editable and can_edit
        except SpaceProfileError as exc:
            period_error = str(exc)
        except Exception as exc:
            logger.error('Space snapshot query failed error_type=%s', type(exc).__name__)
            data_error = 'ไม่สามารถโหลดข้อมูลพื้นที่ได้ กรุณาลองใหม่อีกครั้ง'
    rows.sort(key=lambda row: str(row.get('SubArea_id') or ''))
    for row in rows:
        row['details_complete'] = all(str(row.get(field) or '').strip() for field in (
            'Floor_BI', 'Shop_Sell_BI', 'Business_Types_BI', 'Shop_name_BI', 'Objective_Desc_BI',
        ))
    selected_id = subarea_id or ''
    selected_space = next((row for row in rows if str(row['SubArea_id']) == selected_id), None)
    filter_form = SpaceFilterForm(filter_params, options=space_filter_options(rows))
    filters_valid = filter_form.is_valid()
    filtered_rows = filter_space_rows(rows, filter_form.cleaned_data) if filters_valid else []
    page_obj = Paginator(filtered_rows, 20).get_page(params.get('page'))
    if details_form is None:
        selected = selected_space or {}
        details_form = SpaceDetailsForm(initial={
            'floor': selected.get('Floor_BI'), 'products': selected.get('Shop_Sell_BI'),
            'business_type': selected.get('Business_Types_BI'), 'shop_name': selected.get('Shop_name_BI'),
            'purpose': selected.get('Objective_Desc_BI'),
        })
    base_query = {'month': month, 'year': year_be, 'tab': tab, 'period': target_date.isoformat()}
    list_query = urlencode({**base_query, **filter_params})
    return_query = urlencode({**base_query, **filter_params, 'page': page_obj.number})
    return render(request, 'meters/space_profile_detail.html' if subarea_id is not None else 'meters/space_profile_preview.html', {
        'return_url': f"{reverse('space_profile_preview')}?{return_query}",
        'list_query': list_query,
        'clear_filter_url': '?' + urlencode(base_query),
        'filter_form': filter_form,
        'filter_params': filter_params,
        'filter_error': not filters_valid,
        'has_filters': any(filter_params.values()),
        'total_count': len(rows),
        'tab': tab,
        'active_period_label': f'{THAI_MONTHS[default_date.month - 1]} {default_date.year + 543}',
        'closed_periods': [{'value': d.isoformat(), 'label': f'{THAI_MONTHS[d.month - 1]} {d.year + 543}'} for d in closed_dates],
        'selected_period': target_date.isoformat(),
        'has_history': bool(closed_dates),
        'closed': closed, 'editable': editable,
        'reopened': reopened,
        'incomplete_count': sum(not row['details_complete'] for row in filtered_rows),
        'complete_count': sum(row['details_complete'] for row in filtered_rows),
        'action_error': action_error,
        'details_form': details_form,
        'saved': request.GET.get('result') == 'save',
        'page_obj': page_obj,
        'selected_space': selected_space,
        'data_error': data_error,
        'selection_error': bool(subarea_id is not None and not selected_space and not data_error and not period_error),
        'months': list(enumerate(THAI_MONTHS, start=1)),
        'years': sorted(set(range(today.year + 543 - 10, today.year + 543 + 2)) | {year_be}, reverse=True),
        'selected_month': month,
        'selected_year': year_be,
        'period_label': f'{THAI_MONTHS[month - 1]} {year_be}',
        'snapshot_date_label': f'{target_date.day} {THAI_MONTHS[month - 1]} {year_be}',
        'target_date_value': target_date.strftime('%Y%m%d'),
        'period_error': period_error,
    })
