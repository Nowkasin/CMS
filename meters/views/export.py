# meters/views/export.py
import datetime

from django.http import HttpResponse

from .. import services


def export_meters_excel(request):
    """
    ใช้ query เดียวกับที่ตาราง dashboard ใช้แสดงผล (fetch_subareas + search)
    เพื่อให้ข้อมูลที่ export ตรงกับสิ่งที่ผู้ใช้เห็นบนจอตอนกดปุ่ม
    หมายเหตุ: type_filter (?type=8/9) ยังไม่ได้ผูกกับ fetch_subareas() ในหน้า dashboard เอง
    (ตารางบนจอไม่ได้กรองตาม type อยู่แล้วในตอนนี้) จึง export ไม่กรองตาม type ด้วยเหมือนกัน
    เพื่อให้ผลลัพธ์ตรงกับที่เห็นจริงบนตาราง
    """
    search = request.GET.get('q', '')
    subareas = services.fetch_subareas(search)
    wb = services.build_subareas_workbook(subareas)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"meters_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response