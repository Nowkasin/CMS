"""ศูนย์กลาง mapping ระหว่างสิทธิ์เมนู K2 กับ URL ของ Django"""

PERMISSION_HOME_ROUTES = (
    ('meter_management', 'meter_list'),
    ('excel_upload', 'step1'),
    ('excel_download', 'download_form'),
    ('phase_management', 'phase_list'),
    ('dashboard_view', 'dashboard'),
    ('contract_termination', 'termination_search'),
    ('activity_log_view', 'activity_log'),
    ('invoice_print', 'invoice_search'),
    ('dishwash_fee', 'dishwash'),
)

PERMISSION_LABELS = {
    'meter_management': 'จัดการมิเตอร์',
    'excel_upload': 'อัปโหลดไฟล์',
    'excel_download': 'ดาวน์โหลด Excel',
    'phase_management': 'จัดการระบบไฟฟ้า',
    'dashboard_view': 'แดชบอร์ด',
    'contract_termination': 'ยกเลิกสัญญา',
    'activity_log_view': 'ประวัติการใช้งาน',
    'invoice_print': 'ใบแจ้งหนี้',
    'dishwash_fee': 'ค่าล้างจาน',
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

    'invoice_search': 'invoice_print',
    'invoice_print': 'invoice_print',

    'dishwash': 'dishwash_fee',
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


# --------------------------------------------------------------------------
# "ดูในมุมมองกลุ่ม" (ผู้ดูแลระบบจำลองสิทธิ์เมนูของกลุ่ม K2 อื่น แบบอ่านอย่างเดียว)
#
# ระหว่างจำลอง cms_permissions / cms_home_url เป็นของกลุ่มที่เลือก ส่วนของจริงพักไว้ที่
# VIEW_AS_REAL_KEY -- cms_groups ไม่ถูกแตะ จึงตรวจความเป็นผู้ดูแลจากกลุ่มจริงได้ตลอด
# CMSMenuPermissionMiddleware ปฏิเสธทุก POST ระหว่างจำลอง ยกเว้น VIEW_AS_ALLOWED_POST
# --------------------------------------------------------------------------
VIEW_AS_KEY = 'cms_view_as'            # {'id', 'name', 'permissions'} ของกลุ่มที่จำลอง
VIEW_AS_REAL_KEY = 'cms_view_as_real'  # {'permissions', 'home_url'} ของจริงก่อนจำลอง
# หน้าเฉพาะผู้ดูแลระบบ -- ตรวจจากกลุ่มจริง ไม่ใช่สิทธิ์เมนู (จึงเปิดได้แม้กำลังจำลองกลุ่มอื่น)
ADMIN_URL_NAMES = frozenset({'view_as', 'view_as_start', 'view_as_stop'})
VIEW_AS_ALLOWED_POST = frozenset({'view_as_start', 'view_as_stop', 'logout'})


def is_cms_admin(session):
    """ผู้ใช้อยู่ในกลุ่ม settings.CMS_ADMIN_GROUP_IDS หรือไม่ (จาก cms_groups ที่ได้ตอนล็อกอิน)"""
    from django.conf import settings

    admin_ids = set(getattr(settings, 'CMS_ADMIN_GROUP_IDS', []))
    return any(str(g.get('id', '')).upper() in admin_ids for g in session.get('cms_groups') or [])


def start_view_as(session, group):
    """เริ่มจำลองสิทธิ์ของ group ({'id','name','permissions'}) -- เรียกซ้ำเพื่อเปลี่ยนกลุ่มได้"""
    if VIEW_AS_KEY not in session:
        session[VIEW_AS_REAL_KEY] = {
            'permissions': session.get('cms_permissions') or {},
            'home_url': session.get('cms_home_url') or '',
        }
    session[VIEW_AS_KEY] = {'id': group['id'], 'name': group['name'],
                            'permissions': dict(group['permissions'])}
    session['cms_permissions'] = dict(group['permissions'])
    session['cms_home_url'] = permission_home_url(session['cms_permissions'])


def stop_view_as(session):
    """คืนสิทธิ์จริง -- คืนชื่อกลุ่มที่เคยจำลอง (None ถ้าไม่ได้จำลองอยู่)"""
    current = session.pop(VIEW_AS_KEY, None)
    real = session.pop(VIEW_AS_REAL_KEY, None)
    if real is not None:
        session['cms_permissions'] = real.get('permissions') or {}
        session['cms_home_url'] = real.get('home_url') or permission_home_url(session['cms_permissions'])
    return current['name'] if current else None


def reapply_view_as(session):
    """
    เรียกหลัง store_access_in_session ตอนดึงสิทธิ์ใหม่จาก K2 เป็นระยะ
    ไม่อย่างนั้นสิทธิ์จะเด้งกลับเป็นของจริงกลางคัน -- เก็บสิทธิ์ใหม่ไว้เป็น "ของจริง" แล้วจำลองต่อ
    ถ้าไม่ได้เป็นผู้ดูแลระบบแล้ว ให้เลิกจำลองทันที
    """
    current = session.get(VIEW_AS_KEY)
    if not current:
        return
    if not is_cms_admin(session):
        session.pop(VIEW_AS_KEY, None)
        session.pop(VIEW_AS_REAL_KEY, None)
        return
    session[VIEW_AS_REAL_KEY] = {
        'permissions': session.get('cms_permissions') or {},
        'home_url': session.get('cms_home_url') or '',
    }
    session['cms_permissions'] = dict(current['permissions'])
    session['cms_home_url'] = permission_home_url(session['cms_permissions'])
