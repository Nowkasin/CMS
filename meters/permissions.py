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


def first_allowed_url_name(permissions):
    """คืนชื่อ URL แรกที่ผู้ใช้มีสิทธิ์ หรือ None เมื่อไม่มีสิทธิ์เมนู"""
    for permission, url_name in PERMISSION_HOME_ROUTES:
        if permissions.get(permission):
            return url_name
    return None
