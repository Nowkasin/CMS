"""ศูนย์กลาง mapping ระหว่างสิทธิ์เมนู K2 กับ URL ของ Django"""

PERMISSION_HOME_ROUTES = (
    ('meter_management', 'meter_list'),
    ('excel_upload', 'step1'),
    ('excel_download', 'download_form'),
    ('phase_management', 'phase_list'),
    ('dashboard_view', 'dashboard'),
    ('contract_termination', 'termination_search'),
    ('activity_log_view', 'activity_log'),
)

PERMISSION_LABELS = {
    'meter_management': 'จัดการมิเตอร์',
    'excel_upload': 'อัปโหลดไฟล์',
    'excel_download': 'ดาวน์โหลด Excel',
    'phase_management': 'จัดการระบบไฟฟ้า',
    'dashboard_view': 'แดชบอร์ด',
    'contract_termination': 'ยกเลิกสัญญา',
    'activity_log_view': 'ประวัติการใช้งาน',
}

URL_PERMISSION_MAP = {
    # นำเข้า Excel ทุกขั้นใช้สิทธิ์เดียวกัน เพื่อไม่ให้ข้ามขั้นด้วย URL โดยตรง
    'step1': 'excel_upload',
    'step2': 'excel_upload',
    'step3': 'excel_upload',
    'step4': 'excel_upload',
    'restart': 'excel_upload',

    'dashboard': 'dashboard_view',
    'edit_meter': 'dashboard_view',
    'export_meters': 'dashboard_view',

    'termination_search': 'contract_termination',
    'termination_detail': 'contract_termination',
    'termination_toggle': 'contract_termination',
    'termination_toggle_all': 'contract_termination',
    'termination_delete': 'contract_termination',
    'termination_close_meters': 'contract_termination',

    'activity_log': 'activity_log_view',

    'download_form': 'excel_download',
    'download_excel': 'excel_download',

    'meter_list': 'meter_management',
    'meter_new': 'meter_management',
    'meter_edit': 'meter_management',

    'phase_list': 'phase_management',
    'phase_new': 'phase_management',
    'phase_edit': 'phase_management',
}

PUBLIC_URL_NAMES = frozenset({'login', 'logout', 'no_permission'})
# หน้าที่เปิดได้เมื่อมีสิทธิ์อย่างน้อยหนึ่งเมนู (ไม่ผูกกับเมนูใดเมนูหนึ่ง)
# help = คู่มือการใช้งาน -- เนื้อหาในหน้ากรองตามสิทธิ์อีกชั้น (views/help.py)
HOME_URL_NAMES = frozenset({'home', 'help'})


def first_allowed_url_name(permissions):
    """คืน URL name แรกตามลำดับเมนูที่ผู้ใช้ได้รับสิทธิ์"""
    for permission, url_name in PERMISSION_HOME_ROUTES:
        if permissions.get(permission):
            return url_name
    return None


def permission_home_url(permissions):
    """URL ของเมนูแรกที่มีสิทธิ์ -- ไม่มีสิทธิ์เมนูใดเลยไปหน้า no_permission"""
    from django.urls import reverse

    return reverse(first_allowed_url_name(permissions) or 'no_permission')


# เวลาตรวจสิทธิ์ล่าสุดใน session -- ใช้คู่กับ CMS_ACCESS_REFRESH_SECONDS ใน settings
ACCESS_CHECKED_AT_KEY = 'cms_access_checked_at'


def store_access_in_session(session, access):
    """
    เก็บตัวตน/กลุ่ม/สิทธิ์เมนูจาก fetch_user_access() ลง session

    ใช้ทั้งตอนล็อกอิน และตอน CMSMenuPermissionMiddleware ดึงสิทธิ์ใหม่จาก K2 เป็นระยะ
    (key ใน session เหล่านี้ถูกอ่านโดย sidebar/top nav และ middleware -- ห้ามเปลี่ยนชื่อ)
    """
    import time

    session['cms_person_id'] = access.get('person_id') or ''
    session['cms_display_name'] = access.get('display_name') or ''
    session['cms_groups'] = access.get('groups') or []
    session['cms_has_access'] = bool(access.get('has_cms_access'))
    session['cms_menus'] = access.get('menus') or []
    session['cms_menu_ids'] = access.get('menu_ids') or []
    session['cms_permissions'] = access.get('permissions') or {}
    session['cms_home_url'] = permission_home_url(session['cms_permissions'])
    session[ACCESS_CHECKED_AT_KEY] = int(time.time())
