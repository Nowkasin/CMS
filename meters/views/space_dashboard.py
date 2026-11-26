import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..services.space_profile import get_period_navigation, load_space_period, SpaceProfileError
from ..services.space_dashboard import summarize_spaces, grouped_spaces, dashboard_reference_data
from .dashboard import THAI_MONTHS


logger = logging.getLogger(__name__)


@require_GET
def space_dashboard(request):
    if not request.session.get('cms_permissions', {}).get('space_dashboard_view'):
        return render(request, 'meters/404.html', status=404)
    context = {}
    try:
        active, closed = get_period_navigation()
        dates = sorted(set(closed + ([active] if active else [])), reverse=True)
        selected = request.GET.get('period')
        target = next((day for day in dates if day.isoformat() == selected), None) if selected else (active or next(iter(dates), None))
        context['periods'] = [{'value': day.isoformat(), 'label': f'{THAI_MONTHS[day.month - 1]} {day.year + 543}'} for day in dates]
        if selected and target is None:
            raise SpaceProfileError('ไม่พบรอบข้อมูลที่เลือก')
        if target:
            period = load_space_period(target)
            rows = period['rows']
            summary = summarize_spaces(rows)
            locations, areas, months = dashboard_reference_data(target.year)
            if not period['closed']:
                months[target.month] = rows
            trend = [{'label': name, 'selected': index == target.month,
                      'summary': summarize_spaces(months[index]) if index in months else None}
                     for index, name in enumerate(THAI_MONTHS, 1)]
            context.update({
                'selected_period': target.isoformat(), 'period_label': f'{THAI_MONTHS[target.month - 1]} {target.year + 543}',
                'year_be': target.year + 543, 'closed': period['closed'], 'summary': summary, 'trend': trend,
                'groups': [
                    {'title': 'สรุปตามวิทยาเขต / สถานที่ตั้ง', 'rows': grouped_spaces(rows, ('Location_id',), locations)},
                    {'title': 'สรุปตามประเภทธุรกิจ', 'rows': grouped_spaces(rows, ('Business_Types_BI',))},
                    {'title': 'สรุปตามอาคาร / พื้นที่เช่า', 'rows': grouped_spaces(rows, ('Location_id', 'Area_id'), areas)},
                ],
                'cards': [('พื้นที่ทั้งหมด', summary['total']), ('เช่าอยู่', summary['occupied']),
                          ('ว่าง', summary['vacant']), ('สถานะอื่น / ไม่ระบุ', summary['other'])],
                'ring_offset': 100 - (summary['rate'] or 0),
            })
    except SpaceProfileError as exc:
        context['error'] = str(exc)
    except Exception as exc:
        logger.error('Space dashboard read failed error_type=%s', type(exc).__name__)
        context['error'] = 'ไม่สามารถโหลดข้อมูลสรุปได้ กรุณาลองใหม่'
    return render(request, 'meters/space_dashboard.html', context)
