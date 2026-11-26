import logging

from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..access_control import is_cms_admin
from ..forms import SpacePeriodActionForm
from ..services.space_profile import (
    list_space_periods, close_space_period, reopen_space_period, SpaceProfileError,
)
from .dashboard import THAI_MONTHS


logger = logging.getLogger(__name__)


@require_http_methods(['GET', 'POST'])
def system_settings(request):
    if not is_cms_admin(request):
        return render(request, 'meters/404.html', status=404)
    error = ''
    if request.method == 'POST':
        form = SpacePeriodActionForm(request.POST)
        if form.is_valid():
            try:
                period = form.cleaned_data['period']
                if form.cleaned_data['action'] == 'reopen':
                    reopen_space_period(period, form.cleaned_data['reason'], request.user.get_username())
                else:
                    close_space_period(period, request.user.get_username())
                return redirect(reverse('system_settings') + '?updated=1#space-periods')
            except SpaceProfileError as exc:
                error = str(exc)
            except Exception as exc:
                logger.error('Period setting failed error_type=%s', type(exc).__name__)
                error = 'เปลี่ยนสถานะรอบไม่สำเร็จ กรุณาลองใหม่'
        else:
            error = 'กรุณาตรวจสอบรอบข้อมูลและเหตุผลเปิดรอบ (ไม่เกิน 500 อักขระ)'
    periods = []
    try:
        periods = list_space_periods()
        working = min((row['Period_date'] for row in periods if row['Period_status'] == 'OPEN'), default=None)
        today = timezone.localdate()
        for row in periods:
            day = row['Period_date']
            row['label'] = f'{THAI_MONTHS[day.month - 1]} {day.year + 543}'
            row['date_value'] = day.isoformat()
            row['can_close'] = row['Period_status'] == 'OPEN' and day == working and day <= today
            row['working'] = day == working
    except Exception as exc:
        logger.error('Period settings read failed error_type=%s', type(exc).__name__)
        error = error or 'ไม่สามารถโหลดรอบข้อมูลได้ กรุณาลองใหม่'
    return render(request, 'meters/system_settings.html', {
        'periods': periods, 'error': error, 'updated': request.GET.get('updated') == '1',
    })
