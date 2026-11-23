from django.conf import settings
from django.urls import path, include

# ให้ Django รับ /cms/... โดยตรงเมื่อกำหนด DJANGO_SCRIPT_NAME=/cms
# ถ้าค่าเป็นค่าว่าง ระบบยังทำงานที่ root URL เหมือนเดิม
_url_prefix = f'{settings.URL_PREFIX}/' if settings.URL_PREFIX else ''

urlpatterns = [
    path(_url_prefix, include('meters.urls')),
]

handler404 = 'meters.views.errors.page_not_found'
