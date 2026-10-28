# meters/middleware.py
"""
บันทึก log เหตุการณ์ของทุกเมนูแบบรวมศูนย์ (เขียนลง dbo.Contract_activity_log)

หลักคิด: แทนที่จะแก้ทุก view ให้เรียก log เอง ดักที่ทางเข้าเดียว
  1) process_view  -- ก่อน view ทำงาน: รู้ว่าเป็น URL ไหน และ "ดึงข้อมูลเดิมเก็บไว้" (snapshot ก่อนแก้)
  2) หลัง view ทำงาน -- ดึงข้อมูลอีกครั้งแล้ว "เทียบก่อน-หลัง"
       ไม่มีอะไรเปลี่ยน  -> ไม่ลง log (กดบันทึกเฉยๆ / view ล้มเหลวแต่ redirect กลับ)
       มีอะไรเปลี่ยน     -> ลง log พร้อมข้อความ "เลขมิเตอร์ 123 → 456 · ปิดใช้งาน"
  ความสำเร็จจึงตัดสินจาก "ข้อมูลเปลี่ยนจริง" ไม่ใช่จากการเดาว่า response เป็น redirect

ที่ไม่ผ่าน middleware นี้ (EXCLUDE) เพราะมี log ของตัวเองอยู่แล้ว:
  - ยกเลิกสัญญา (บันทึก/ลบ/ปิดการตั้งหนี้มิเตอร์) -- SP เขียน log ในทรานแซกชันเดียวกับงานหลัก
  - ติ๊กงวด -- ตั้งใจไม่ลง log (เกิดบ่อย เป็นแค่ข้อมูลอ้างอิง)
  - นำเข้าไฟล์ Excel (step3) -- commit_staged_rows เขียน log เอง
  - Master ระบบไฟฟ้า -- phase_master.py เขียน log เอง (มีรายละเอียดชื่อเดิม → ชื่อใหม่)
  - ขั้นตอนที่แค่พักข้อมูลใน session (step1/step2/step4/restart) และ login/logout

POST ที่ไม่อยู่ในทั้งตารางลงทะเบียนและ EXCLUDE (เช่นเมนูใหม่ที่เพิ่มภายหลังแล้วลืมมาลงทะเบียน)
จะถูกลง log เป็น "การดำเนินการอื่น" พร้อมชื่อ URL เมื่อ redirect สำเร็จ -- ไม่หลุดเงียบ

ข้อผิดพลาดใดๆ ในไฟล์นี้ถูกกลืนลง logger ('meters.middleware') ไม่ทำให้หน้าเว็บล้ม
"""
import logging

from .services import activity_log as activity
from .services import (
    fetch_meter_by_id,
    fetch_readings_for_meters,
    fetch_subarea_meters,
)

logger = logging.getLogger(__name__)

# url name ที่ไม่ต้องดักเลย (ดูเหตุผลที่หัวไฟล์)
EXCLUDE = frozenset({
    'login', 'logout',
    'step1', 'step2', 'step3', 'step4', 'restart',
    'termination_detail', 'termination_toggle', 'termination_toggle_all',
    'termination_delete', 'termination_close_meters',
    'phase_new', 'phase_edit',
})


# --------------------------------------------------------------------------
# ตัวช่วยเทียบค่าก่อน-หลัง
# --------------------------------------------------------------------------
def _norm(value):
    """ทำให้ค่าเทียบกันได้: None กับ '' ถือว่าเท่ากัน, ตัดช่องว่างหัวท้าย"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return value


def _fmt(value):
    if value is None or value == '':
        return '-'
    if isinstance(value, bool):
        return 'เปิดใช้งาน' if value else 'ปิดใช้งาน'
    return str(value).strip()


def _diff(before, after, labels):
    """คืนรายการข้อความ 'ป้าย เดิม → ใหม่' เฉพาะฟิลด์ที่เปลี่ยนจริง"""
    changes = []
    for key, label in labels.items():
        old, new = before.get(key), after.get(key)
        if _norm(old) != _norm(new):
            changes.append(f'{label} {_fmt(old)} → {_fmt(new)}')
    return changes


def _is_attachment(response):
    return (response.status_code == 200
            and 'attachment' in (response.get('Content-Disposition') or '').lower())


def _is_redirect(response):
    return response.status_code in (301, 302, 303, 307, 308)


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# จัดการมิเตอร์ (meter_new / meter_edit -> views.meter_form)
# --------------------------------------------------------------------------
METER_FIELDS = {
    'SubArea_id': 'พื้นที่ย่อย',
    'Meter_no': 'เลขมิเตอร์',
    'Phase_type': 'ระบบไฟฟ้า',
    'Meter_remark': 'หมายเหตุ',
    'UseOrNot': 'การใช้งาน',
}


def _meter_form_before(request, kwargs):
    meter_id = kwargs.get('meter_id')
    return fetch_meter_by_id(meter_id) if meter_id else None


def _meter_form_build(request, kwargs, before, response):
    meter_id = kwargs.get('meter_id')

    if not meter_id:
        # เพิ่มใหม่: ยังไม่รู้ Meter_id ที่เพิ่งสร้าง (view ไม่ได้บอกกลับ) จึงยืนยันได้แค่จาก redirect
        # และใช้ค่าที่ POST มาเป็นรายละเอียด -- ฟอร์มที่กรอกผิดจะ render หน้าเดิมกลับ (ไม่ redirect)
        if not _is_redirect(response):
            return None
        post = request.POST
        type_label = 'น้ำ' if post.get('meter_type_cd') == '9' else 'ไฟ'
        meter_no = (post.get('meter_no') or '').strip()
        return {
            'action': activity.ACTION_METER_CREATE,
            'ref_text': meter_no or f'มิเตอร์{type_label}ใหม่',
            'subarea_id': post.get('subarea_id') or None,
            'detail': (f'เพิ่มมิเตอร์{type_label} · เลข {meter_no or "(ยังไม่มี/รอ Gen เลข)"}'
                       f' · พื้นที่ย่อย {post.get("subarea_id") or "-"}'),
        }

    after = fetch_meter_by_id(meter_id)
    if not before or not after:
        return None
    changes = _diff(before, after, METER_FIELDS)
    if not changes:
        return None   # ไม่มีอะไรเปลี่ยน
    only_toggle = len(changes) == 1 and changes[0].startswith('การใช้งาน')
    return {
        'action': activity.ACTION_METER_TOGGLE if only_toggle else activity.ACTION_METER_UPDATE,
        'ref_text': after.get('Meter_no') or f'Meter #{meter_id}',
        'meter_id': int(meter_id),
        'subarea_id': after.get('SubArea_id'),
        'detail': ' · '.join(changes),
    }


# --------------------------------------------------------------------------
# แดชบอร์ด > แก้ไขมิเตอร์ + เลขอ่านรายรอบ (edit_meter)
# --------------------------------------------------------------------------
SUBAREA_FIELDS = {
    'water_no': 'เลขมิเตอร์น้ำ',
    'electric_no': 'เลขมิเตอร์ไฟ',
    'electric_phase': 'ระบบไฟฟ้า',
    'water_before': 'น้ำ เลขอ่านก่อน',
    'water_after': 'น้ำ เลขอ่านหลัง',
    'electric_before': 'ไฟ เลขอ่านก่อน',
    'electric_after': 'ไฟ เลขอ่านหลัง',
}


def _snapshot_subarea(subarea_id, year, month):
    info = fetch_subarea_meters(subarea_id)
    if not info:
        return None
    water, electric = info.get('water'), info.get('electric')

    readings = {}
    ids = [m['Meter_id'] for m in (water, electric) if m]
    if ids and year and month:
        # ถือว่า billing_year ที่ฟอร์มส่งมาเป็น พ.ศ. (ตรงกับพารามิเตอร์ billing_year_be ของ service)
        readings = fetch_readings_for_meters(ids, year, month)

    def reading(meter, key):
        return readings.get(int(meter['Meter_id']), {}).get(key) if meter else None

    return {
        'contract_id': info.get('contract_no'),   # contract_no ใน service คือ Contract_id (int)
        'water_no': water.get('Meter_no') if water else None,
        'electric_no': electric.get('Meter_no') if electric else None,
        'electric_phase': electric.get('Phase_type') if electric else None,
        'water_before': reading(water, 'Reading_before'),
        'water_after': reading(water, 'Reading_after'),
        'electric_before': reading(electric, 'Reading_before'),
        'electric_after': reading(electric, 'Reading_after'),
    }


def _period_from_post(request):
    return _to_int(request.POST.get('billing_year')), _to_int(request.POST.get('billing_month'))


def _edit_meter_before(request, kwargs):
    year, month = _period_from_post(request)
    return _snapshot_subarea(kwargs.get('subarea_id'), year, month)


def _edit_meter_build(request, kwargs, before, response):
    subarea_id = kwargs.get('subarea_id')
    year, month = _period_from_post(request)
    after = _snapshot_subarea(subarea_id, year, month)
    if not before or not after:
        return None
    changes = _diff(before, after, SUBAREA_FIELDS)
    if not changes:
        return None
    detail = ' · '.join(changes)
    if month and year:
        detail = f'รอบบิล {month}/{year} -- {detail}'
    return {
        'action': activity.ACTION_READING_SAVE,
        'ref_text': f'SubArea {subarea_id}',
        'subarea_id': subarea_id,
        'contract_id': after.get('contract_id'),
        'detail': detail,
    }


# --------------------------------------------------------------------------
# นำข้อมูลออก (ดาวน์โหลด Excel / ส่งออกมิเตอร์) -- ไม่มีข้อมูลเปลี่ยน ตัดสินจากว่าส่งไฟล์กลับ
# --------------------------------------------------------------------------
def _download_build(request, kwargs, before, response):
    if not _is_attachment(response):
        return None
    post = request.POST
    month, year = post.get('month'), post.get('year')
    selected = len(post.getlist('selected_rows'))
    return {
        'action': activity.ACTION_DOWNLOAD_EXCEL,
        'ref_text': f'{month}/{year}' if month and year else None,
        'detail': f'ดาวน์โหลด Excel รอบบิล {month or "-"}/{year or "-"} · เลือก {selected} แถว',
    }


def _export_build(request, kwargs, before, response):
    if not _is_attachment(response):
        return None
    type_filter = request.GET.get('type', 'all')
    type_label = {'9': 'เฉพาะน้ำ', '8': 'เฉพาะไฟ'}.get(type_filter, 'ทุกประเภท')
    search = (request.GET.get('q') or '').strip()
    detail = f'ส่งออกมิเตอร์เป็น Excel · {type_label}'
    if search:
        detail += f' · ค้นหา "{search}"'
    return {
        'action': activity.ACTION_EXPORT_METERS,
        'ref_text': search or None,
        'detail': detail,
    }


# --------------------------------------------------------------------------
# POST ที่ไม่อยู่ในตารางลงทะเบียน -> ลงเป็น "การดำเนินการอื่น" (กันเมนูใหม่หลุดเงียบ)
# --------------------------------------------------------------------------
def _fallback_build(request, kwargs, before, response):
    if not (_is_redirect(response) or _is_attachment(response)):
        return None
    name = request.resolver_match.url_name if request.resolver_match else '-'
    return {
        'action': activity.ACTION_OTHER,
        'ref_text': name,
        'detail': f'{request.method} {request.path} (ยังไม่ได้ลงทะเบียนใน middleware)',
    }


# ตารางลงทะเบียน: ชื่อ URL -> วิธีดึงข้อมูลก่อน (before) + วิธีประกอบ log หลังทำงาน (build)
# เมนูใหม่ที่ต้องการรายละเอียดเฉพาะ ให้เพิ่มที่นี่
REGISTRY = {
    'meter_new':      {'methods': ('POST',), 'before': _meter_form_before, 'build': _meter_form_build},
    'meter_edit':     {'methods': ('POST',), 'before': _meter_form_before, 'build': _meter_form_build},
    'edit_meter':     {'methods': ('POST',), 'before': _edit_meter_before, 'build': _edit_meter_build},
    'download_excel': {'methods': ('POST',), 'before': None, 'build': _download_build},
    'export_meters':  {'methods': ('GET',),  'before': None, 'build': _export_build},
}
FALLBACK = {'methods': ('POST',), 'before': None, 'build': _fallback_build}


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        state = getattr(request, '_activity_state', None)
        if state:
            try:
                self._finish(request, response, state)
            except Exception:
                logger.exception('ActivityLogMiddleware: ประกอบ/เขียน log ไม่สำเร็จ')
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        request._activity_state = None
        try:
            request._activity_state = self._start(request, view_kwargs)
        except Exception:
            logger.exception('ActivityLogMiddleware: เก็บข้อมูลก่อนทำงานไม่สำเร็จ')
        return None

    @staticmethod
    def _start(request, kwargs):
        match = request.resolver_match
        if not match or not match.url_name or match.url_name in EXCLUDE:
            return None
        if not request.user.is_authenticated:
            return None

        spec = REGISTRY.get(match.url_name)
        if spec is None:
            if request.method != 'POST':
                return None
            spec = FALLBACK
        elif request.method not in spec['methods']:
            return None

        before = spec['before'](request, kwargs) if spec['before'] else None
        return {'spec': spec, 'before': before, 'kwargs': kwargs}

    @staticmethod
    def _finish(request, response, state):
        if response.status_code >= 400:
            return
        data = state['spec']['build'](request, state['kwargs'], state['before'], response)
        if not data:
            return
        action = data.pop('action')
        activity.log_activity_safe(action, request.user.get_username(), **data)