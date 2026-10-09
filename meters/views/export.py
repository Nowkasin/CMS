# meters/views/export.py
import datetime

from django.http import HttpResponse

from .. import services


def export_meters_excel(request):
    """
    ใช้ query เดียวกับที่ตาราง dashboard ใช้แสดงผล (fetch_subareas + search + type)
    เพื่อให้ข้อมูลที่ export ตรงกับสิ่งที่ผู้ใช้เห็นบนจอตอนกดปุ่ม

    ตอนนี้ fetch_subareas() กรองตามประเภทมิเตอร์ได้แล้ว จึงส่ง ?type= ต่อเข้าไปด้วย
    (ก่อนหน้านี้ตารางบนจอยังไม่กรองตาม type เลย จึงตั้งใจไม่ส่งต่อ -- หมายเหตุนั้นหมดอายุแล้ว)
    """
    search = request.GET.get('q', '')
    type_filter = request.GET.get('type', 'all')
    if type_filter not in ('all', '8', '9'):
        type_filter = 'all'
    subareas = services.fetch_subareas(search, type_filter)
    wb = services.build_subareas_workbook(subareas)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"meters_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response