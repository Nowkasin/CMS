# meters/views/termination.py
import datetime
import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render, redirect

from .. import services
from .dashboard import THAI_MONTHS

DEFAULT_USER = 'web_upload'

# ค่า Termination_case -- ยืนยันให้ตรงกับ sp_Contract_Termination_Save แล้ว
# (ดู sql/sp_Contract_Termination_FixCaseMapping.sql -- เดิม SP คาดหวังค่าสลับกับที่นี่
#  ทำให้ได้จำนวนเดือนผ่อนผันและสถานะสัญญาผิด จึงแก้ SP ให้ตรงกับเอกสาร requirement)
#
#   case 1 = ยกเลิกก่อนครบอายุ      -> ผ่อนผัน 2 เดือน, สถานะสัญญา '5' (ยกเลิกสัญญา)
#   case 2 = สิ้นสุดตามอายุ ไม่ต่อ  -> ผ่อนผัน 1 เดือน, สถานะสัญญา '4' (ไม่ต่อสัญญา)
CASE_CANCEL_BEFORE_END = '1'
CASE_END_NO_RENEW = '2'

TERMINATION_CASES = {
    CASE_CANCEL_BEFORE_END: 'ยกเลิกสัญญาก่อนครบอายุสัญญา (จัดการต่อได้อีก 2 เดือน)',
    CASE_END_NO_RENEW: 'สิ้นสุดสัญญาและไม่ต่อสัญญา (จัดการต่อได้อีก 1 เดือน)',
}

# จำนวนเดือนผ่อนผันต่อ case -- สะท้อนค่าใน sp_Contract_Termination_Save
# (@Buffer_month_count = CASE @Termination_case WHEN 1 THEN 2 ELSE 1)
# ใช้ "เพื่อ preview ในกล่องยืนยันเท่านั้น" ตัวจริงที่บันทึกลง DB คือ SP
# ถ้าแก้ค่าใน SP ต้องมาแก้ที่นี่ด้วย
CASE_BUFFER_MONTHS = {
    CASE_CANCEL_BEFORE_END: 2,
    CASE_END_NO_RENEW: 1,
}


def _sp_error_message(exc, fallback):
    """
    ดึงข้อความ RAISERROR ที่ SP เขียนไว้ออกมาแสดงให้ผู้ใช้

    SP ชุดยกเลิกสัญญาเขียนข้อความเป็นภาษาไทยสำหรับผู้ใช้อยู่แล้ว (เช่น "สัญญานี้มีการบันทึก
    ยกเลิกไปแล้ว...") แต่ pyodbc ห่อด้วยชื่อ driver กับรหัส error เช่น
      ('42000', "[42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]ข้อความจริง (50000) (SQLExecDirectW)")

    แกะเฉพาะกรณีที่เป็น RAISERROR ของเราเอง (native error 50000) เท่านั้น
    error อื่น (เช่น constraint ชน) จะคืน fallback เพราะข้อความดิบมักมีชื่อตาราง/คอลัมน์ติดมา
    ไม่ควรโชว์ให้ผู้ใช้เห็น
    """
    text = str(exc)
    if '(50000)' not in text or '[SQL Server]' not in text:
        return fallback
    msg = text.split('[SQL Server]')[-1]
    msg = re.sub(r"\s*\(\d+\)\s*\(\w+\)\s*[\"')]*\s*$", '', msg).strip()
    return msg or fallback


def _expired_ago_label(end_date, today=None):
    """
    'หมดอายุมานานเท่าไหร่' จาก End_contract -> เช่น '6 ปี 4 เดือน', '3 เดือน', 'เดือนนี้'

    คืน None ถ้ายังไม่หมดอายุหรือไม่มีวันที่
    ข้อมูลจริงมีสัญญาที่เลยกำหนดมา 76 เดือน -- บอกเป็นเดือนล้วนจะอ่านยาก จึงแปลงเป็นปี+เดือน

    นับแบบเดือนปฏิทิน (ไม่ใช่หาร 30 วัน) ให้ตรงกับวิธีคิดงวดของระบบ
    """
    if not end_date:
        return None
    today = today or datetime.date.today()
    if end_date >= today:
        return None

    months = (today.year - end_date.year) * 12 + (today.month - end_date.month)
    # วันที่ในเดือนยังไม่ถึง -> ยังไม่ครบเดือนนั้น
    if today.day < end_date.day:
        months -= 1
    if months <= 0:
        return 'เดือนนี้'

    years, rem = divmod(months, 12)
    parts = []
    if years:
        parts.append(f'{years} ปี')
    if rem:
        parts.append(f'{rem} เดือน')
    return ' '.join(parts)


def _thai_date(value):
    """
    วันที่ -> '1 มิถุนายน 2569' (พ.ศ.) ใช้แสดงช่วงอายุสัญญาบนหน้าจอ
    ตรงกับฟังก์ชัน thaiDate() ใน termination_detail.js คืน None ถ้าไม่ใช่วันที่
    """
    if not value:
        return None
    try:
        return f'{value.day} {THAI_MONTHS[value.month - 1]} {value.year + 543}'
    except (AttributeError, IndexError, TypeError):
        return None


def _period_label(period):
    """
    แปลงงวดรูปแบบ YYYYMM ให้เป็นข้อความไทย เช่น '202702' -> 'กุมภาพันธ์ 2570'

    ปีใน Installment_period / Last_installment_period เป็น ค.ศ. -- ตรงกับ
    Contract_Installment_tr.Contract_Installment_month_year ซึ่งเป็น ค.ศ. ทั้ง 3009 แถว
    (sp_Contract_Installment_CreateAfterTermination เอาค่านี้ไปใส่คอลัมน์นั้นตรงๆ
     จึงต้องเป็น convention เดียวกัน -- ห้ามเปลี่ยนค่าที่เก็บ)

    แต่ "ตอนแสดงผล" ต้องเป็น พ.ศ. เพราะปีที่ผู้ใช้เห็นที่อื่นในระบบนี้เป็น พ.ศ. ทั้งหมด
    (Billing_year_be, Contract_year, _current_year_be) ถ้าโชว์ '202702' ดิบๆ
    ผู้ใช้ไทยมีโอกาสอ่านเป็น พ.ศ. 2702 ซึ่งคลาดไป 175 ปี
    เทมเพลตยังโชว์ค่าดิบกำกับไว้ด้วย เพื่อให้เทียบกับข้อมูลในฐานข้อมูลได้

    คืน None ถ้ารูปแบบไม่ใช่ YYYYMM -> เทมเพลต fallback ไปโชว์ค่าดิบแทน
    """
    text = str(period or '').strip()
    if len(text) != 6 or not text.isdigit():
        return None
    year_ce, month = int(text[:4]), int(text[4:])
    if not 1 <= month <= 12:
        return None
    return f'{THAI_MONTHS[month - 1]} {year_ce + 543}'


# สถานะ workflow ที่ถือว่าสัญญาเสร็จสมบูรณ์แล้ว (จาก dbo.Contract_workflow_status_ms)
#   '40' สัญญาเสร็จสมบูรณ์ / '50' สัญญาเสร็จสมบูรณ์-สิ้นสุด
WORKFLOW_COMPLETE = frozenset({'40', '50'})

# ขอบเขตข้อมูลที่แสดง (?scope=)
#
# ข้อมูลจริงมี 44 จาก 224 สัญญาที่ workflow ยังไม่ถึง '40' (ร่าง / ไม่อนุมัติ /
# ยกเลิกฉบับร่าง) ซึ่งไม่ควรอยู่ในคิวยกเลิกสัญญาเพราะยังไม่มีสัญญาให้ยกเลิก
# และมีข้อมูลทดสอบปนอยู่ชัดเจน ('123456', 'กดกดกดกดกดกด', 'ทดสอบ H2/2563')
#
# แต่กรองด้วย workflow ล้วนไม่ได้: 24 ฉบับในนั้นตั้งหนี้ไปแล้ว (บางฉบับ 53 งวด)
# รวมสัญญา 113 ที่สถานะเป็น 'ยกเลิกสัญญา' อยู่แล้ว -- ถ้ากรองออกจะซ่อนสัญญาที่มี
# ประวัติการเงินจริง จึงถือว่า "เป็นสัญญาจริง" เมื่อ workflow เสร็จสมบูรณ์ "หรือ" มีงวดแล้ว
#
# ไม่ซ่อนถาวร -- สลับไปดูฉบับร่างหรือดูทั้งหมดได้ เพราะคนใช้ระบบยังแยกไม่ออกว่า
# แถวไหนเป็นข้อมูลจริงแถวไหนเป็นข้อมูลทดสอบ
SCOPE_REAL = 'real'
SCOPE_DRAFT = 'draft'
SCOPE_ALL = 'all'

TERMINATION_SCOPES = [
    (SCOPE_REAL, 'สัญญาจริง (เสร็จสมบูรณ์ หรือตั้งหนี้แล้ว)'),
    (SCOPE_DRAFT, 'ฉบับร่าง/ไม่อนุมัติ ที่ยังไม่ตั้งหนี้'),
    (SCOPE_ALL, 'ทั้งหมด'),
]


def _is_real_contract(row):
    """สัญญาจริง = workflow เสร็จสมบูรณ์ หรือมีงวดตั้งหนี้แล้ว (ดูเหตุผลที่ TERMINATION_SCOPES)"""
    return (row.get('Status_workflow__id') in WORKFLOW_COMPLETE
            or bool(row.get('Has_installment')))


# แท็บของหน้ารายการสัญญา -- key คือค่าใน query string (?tab=)
# 'expired' เป็นค่าเริ่มต้นเพราะเป็นเนื้องานจริง: ไล่ปิดสัญญาที่หมดอายุค้างอยู่
TAB_EXPIRED = 'expired'
TAB_UPCOMING = 'upcoming'
TAB_TERMINATED = 'terminated'
TAB_ALL = 'all'

TERMINATION_TABS = [
    (TAB_EXPIRED, 'หมดอายุแล้ว รอบันทึกยกเลิก'),
    (TAB_UPCOMING, 'ยังไม่หมดอายุ'),
    (TAB_TERMINATED, 'ยกเลิก/ปิดสัญญาแล้ว'),
    (TAB_ALL, 'ทั้งหมด'),
]

CONTRACTS_PER_PAGE = 25


def _classify_contract(row, today):
    """
    ติดธงที่หน้ารายการต้องใช้ให้แถวหนึ่งแถว แล้วคืนชื่อแท็บที่แถวนั้นสังกัด

    is_blocked -- ยกเลิกซ้ำไม่ได้ (สถานะปิด/ยกเลิกแล้ว หรือมีรายการยกเลิกในระบบนี้แล้ว)
    is_expired -- คำนวณจาก End_contract ไม่ใช่ Status_contract_id
                  สองอันนี้ไม่ตรงกันใน 199 จาก 222 สัญญา จึงต้องแยกกันให้ชัด

    แท็บจัดตามลำดับนี้:
      ยกเลิกซ้ำไม่ได้ -> terminated (จบแล้ว ไม่ต้องมารกคิวงาน)
      หมดอายุแล้ว     -> expired    (คิวงานที่ทำได้จริง)
      นอกนั้น          -> upcoming

    ใช้ is_blocked ไม่ใช่ Has_termination เป็นตัวแยกแท็บ terminated เพราะข้อมูลจริงมี
    สัญญาที่สถานะเป็น 'ยกเลิกสัญญา' อยู่แล้วแต่ไม่มีแถวใน Contract_termination_tr
    (เช่น Contract_id 113 -- ยกเลิกจากช่องทางอื่น) ถ้าแยกด้วย Has_termination
    สัญญาพวกนี้จะไปโผล่ในคิวงาน แล้วกดเข้าไปเจอฟอร์มที่ถูกปิด = คิวงานมีงานปลอมปน

    สัญญาที่ไม่มี End_contract ไปอยู่ upcoming -- ยังไม่มีหลักฐานว่าหมดอายุ
    """
    end = row.get('End_contract')
    row['is_blocked'] = (
        row.get('Status_contract_id') in services.BLOCKED_CONTRACT_STATUSES
        or bool(row.get('Has_termination'))
    )
    row['is_expired'] = bool(end and end < today)
    row['end_contract_label'] = _thai_date(end)
    row['expired_ago_label'] = _expired_ago_label(end, today)

    if row['is_blocked']:
        return TAB_TERMINATED
    return TAB_EXPIRED if row['is_expired'] else TAB_UPCOMING


def termination_search(request):
    """
    หน้ารายการสัญญาสำหรับงานยกเลิก -- เปิดมาเห็นรายการเลย ไม่ต้องค้นหาก่อน

    เดิมเป็นหน้าค้นหาแบบ POST ที่เปิดมาว่างเปล่า ซึ่งมีปัญหา:
      - ผลค้นหาไม่ผูกกับ URL -> กด back จากหน้า detail แล้วผลหาย ต้องพิมพ์ใหม่
        และ refresh แล้วเบราว์เซอร์เตือนส่งข้อมูลซ้ำ แชร์ลิงก์ก็ไม่ได้
      - ต้องรู้รหัสสัญญามาก่อนจึงหาอะไรได้ ทั้งที่งานจริงคือ "หาสัญญาที่หมดอายุแล้ว
        แต่ยังไม่ได้บันทึกยกเลิก" ซึ่งมี 199 ฉบับ
      - เป็นหน้าเดียวในโปรเจกต์ที่ค้นหาด้วย POST (meter_list ใช้ GET + filter อยู่แล้ว)

    ตอนนี้ทุกอย่างเป็น GET: ?tab=&status=&q=&page= -> back/refresh/แชร์ลิงก์ได้ครบ

    จำนวนบนแท็บนับ "หลังกรองด้วย q และ status แล้ว" เพื่อให้ตัวเลขตรงกับสิ่งที่เห็น
    """
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')
    tab = request.GET.get('tab', TAB_EXPIRED)
    if tab not in dict(TERMINATION_TABS):
        tab = TAB_EXPIRED
    scope = request.GET.get('scope', SCOPE_REAL)
    if scope not in dict(TERMINATION_SCOPES):
        scope = SCOPE_REAL

    rows = services.fetch_contracts_for_termination(search, status_filter)

    # กรองด้วย scope ก่อน แล้วจึงนับแท็บ -- ตัวเลขบนแท็บต้องสอดคล้องกับขอบเขตที่เลือก
    for row in rows:
        row['is_real_contract'] = _is_real_contract(row)
    scope_counts = {
        SCOPE_REAL: sum(1 for r in rows if r['is_real_contract']),
        SCOPE_DRAFT: sum(1 for r in rows if not r['is_real_contract']),
        SCOPE_ALL: len(rows),
    }
    if scope == SCOPE_REAL:
        rows = [r for r in rows if r['is_real_contract']]
    elif scope == SCOPE_DRAFT:
        rows = [r for r in rows if not r['is_real_contract']]

    today = datetime.date.today()
    counts = {key: 0 for key, _label in TERMINATION_TABS}
    for row in rows:
        row['_tab'] = _classify_contract(row, today)
        counts[row['_tab']] += 1
    counts[TAB_ALL] = len(rows)

    visible = rows if tab == TAB_ALL else [r for r in rows if r['_tab'] == tab]

    paginator = Paginator(visible, CONTRACTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    # ประกอบแท็บพร้อมจำนวนให้เสร็จที่นี่ -- เทมเพลต Django index dict ด้วยตัวแปรไม่ได้
    # (counts[key] เขียนในเทมเพลตไม่ได้) ถ้าดันไปทำในเทมเพลตจะได้ hack ที่อ่านไม่รู้เรื่อง
    tabs = [
        {'key': key, 'label': label, 'count': counts[key], 'is_active': key == tab}
        for key, label in TERMINATION_TABS
    ]

    scopes = [
        {'key': key, 'label': label, 'count': scope_counts[key], 'is_active': key == scope}
        for key, label in TERMINATION_SCOPES
    ]

    context = {
        'page_obj': page_obj,
        'contracts': page_obj.object_list,
        'total_visible': len(visible),
        'tabs': tabs,
        'active_tab': tab,
        'scopes': scopes,
        'active_scope': scope,
        'scope_is_default': scope == SCOPE_REAL,
        'search': search,
        'status_filter': status_filter,
        'statuses': services.fetch_contract_statuses(),
    }
    # หมายเหตุ: ลิงก์แบ่งหน้า/แท็บ/แถว ประกอบจากตัวแปรเหล่านี้ในเทมเพลตด้วย |urlencode
    # ไม่ได้ส่ง query string สำเร็จรูปมา เพราะค่าที่ผ่าน urlencode() ของ Python จะถูก
    # autoescape เป็น &amp; แล้วไปปนกับ & ดิบที่พิมพ์ในเทมเพลต ทำให้พารามิเตอร์หลุด
    return render(request, 'meters/termination_search.html', context)


def termination_detail(request, contract_id):
    """
    โชว์ข้อมูลยกเลิกสัญญา (ถ้ามีอยู่แล้ว) + รายการงวดทั้งหมดของสัญญานี้
    + รายละเอียดสัญญา/มิเตอร์ (จาก fetch_contract_meter_detail เดิมที่ใช้กับหน้ามิเตอร์)
    POST ที่นี่ = บันทึกข้อมูลยกเลิก (ไม่ใช่ติ๊กงวด -- งวดแยกไปที่ termination_toggle_installment)

    sp_Contract_Termination_Save ตรวจเงื่อนไขเองหลายข้อแล้ว RAISERROR ออกมา
    view จึงต้อง validate ฝั่งนี้ก่อนเพื่อให้ผู้ใช้เห็นข้อความที่เข้าใจง่าย และครอบ try/except
    กัน error จาก SP หลุดเป็นหน้า 500:
      - @Contract_end_date เป็น DATE ที่ SP ไม่ยอมรับ NULL
      - case ยกเลิกก่อนครบอายุ SP บังคับว่าต้องมี @Notify_date
      - ถ้าสัญญานี้มีข้อมูลยกเลิกอยู่แล้ว SP จะปฏิเสธ (ไม่ให้สร้างซ้ำ)
      - ถ้าสัญญามีสถานะปิด/ยกเลิกอยู่แล้ว SP จะปฏิเสธ
    """
    # ดึงข้อมูลระบุตัวสัญญาก่อนทุกอย่าง -- ไม่พบ = 404
    # เดิมเข้า contract_id ที่ไม่มีจริงได้ แล้วเจอฟอร์มเปล่าที่กดบันทึกแล้วค่อยพัง
    contract = services.fetch_contract_summary(contract_id)
    if not contract:
        raise Http404(f'ไม่พบสัญญา Contract_id {contract_id}')

    # ปิดฟอร์มล่วงหน้าถ้าสถานะสัญญายกเลิกซ้ำไม่ได้ (SP ก็บล็อกอยู่ แต่ให้ผู้ใช้รู้ก่อนกรอก)
    blocked_status = contract.get('Status_contract_id') in services.BLOCKED_CONTRACT_STATUSES

    # ช่วงอายุสัญญาจาก Contract_tr -- ใช้ทั้งแสดงบนหัวหน้า และเติมค่าในฟอร์ม
    contract['start_contract_label'] = _thai_date(contract.get('Start_contract'))
    contract['end_contract_label'] = _thai_date(contract.get('End_contract'))

    # เทียบชื่อลูกค้าในสัญญากับ master ฝั่ง SAP -- ข้อมูลจริงมี 3 สัญญาที่เป็นคนละคนกัน
    # เทียบแบบยุบช่องว่างซ้ำก่อน เพื่อไม่ให้เตือนเพราะเรื่องช่องว่างเฉยๆ (มี 2 แถวแบบนั้น)
    def _squash(value):
        return ' '.join(str(value or '').split())

    sap_name = contract.get('SAP_CompanyName')
    contract['sap_name_differs'] = bool(
        sap_name and _squash(sap_name) != _squash(contract.get('CompanyName'))
    )

    end_contract = contract.get('End_contract')
    # 199 จาก 222 สัญญาที่ยัง active มี End_contract เป็นอดีตไปแล้ว (บางฉบับ 76 เดือน)
    # ต้องบอกให้ชัดว่าค่าที่เติมมาเป็นวันในอดีตจริงตามสัญญา ไม่ใช่ระบบเติมผิด
    end_contract_is_past = bool(end_contract and end_contract < datetime.date.today())
    # "หมดอายุ" เป็นสถานะที่คำนวณจากวันที่ ไม่ใช่ Status_contract_id ที่เก็บในระบบ
    # เทมเพลตต้องแยกป้ายสองอันนี้ให้ชัด ไม่ให้ดูเหมือนระบบขัดแย้งกันเอง
    contract['expired_ago_label'] = _expired_ago_label(end_contract)

    # แยก 2 กอง -- สำคัญ ไม่ใช่เรื่องจัดระเบียบเฉยๆ
    #   form_errors  = ผลการ validate ฟอร์มรอบนี้ ใช้ตัดสินว่าจะบันทึกหรือไม่
    #   notices      = ข้อความจากการกระทำครั้งก่อน (flash/query string) ใช้แสดงผลเท่านั้น
    #
    # เดิมรวมเป็น list เดียวแล้วเช็ค `if not errors:` ก่อนบันทึก ทำให้ข้อความค้างจาก
    # การกระทำครั้งก่อน (เช่นกดปิดการตั้งหนี้มิเตอร์แล้วถูกปฏิเสธ) ไปบล็อกการบันทึก
    # ครั้งถัดไปแบบเงียบๆ -- ผู้ใช้กดบันทึกแล้วไม่มีอะไรเกิดขึ้นและไม่รู้ว่าทำไม
    form_errors = []
    notices = []

    # ข้อความ error จากการติ๊กงวด -- ส่งต่อมาทาง query string เพราะ toggle redirect กลับมาที่นี่
    if request.GET.get('toggle_error'):
        notices.append('เปลี่ยนสถานะงวดไม่สำเร็จ -- กรุณาลองใหม่อีกครั้ง')

    # ข้อความจากการลบรายการยกเลิก/ปิดการตั้งหนี้ -- ฝากไว้ใน session เพราะ view เหล่านั้น
    # redirect กลับมาที่นี่ (ใช้ session ไม่ใช่ query string เพราะข้อความยาวและมาจาก
    # RAISERROR ของ SP)
    #
    # pop เฉพาะตอน GET: ถ้า pop ตอน POST ที่บันทึกสำเร็จแล้ว redirect ออกไป
    # ข้อความจะถูกทิ้งไปโดยไม่เคยแสดงให้ใครเห็น
    flash_error = flash_warning = flash_success = None
    if request.method != 'POST':
        flash_error = request.session.pop('termination_flash_error', None)
        if flash_error:
            notices.append(flash_error)
        flash_warning = request.session.pop('termination_flash_warning', None)
        flash_success = request.session.pop('termination_flash_success', None)

    form = {'termination_case': '', 'contract_end_date': '', 'notify_date': '', 'remark': ''}

    if request.method == 'POST':
        form = {
            'termination_case': request.POST.get('termination_case', '').strip(),
            'contract_end_date': request.POST.get('contract_end_date', '').strip(),
            'notify_date': request.POST.get('notify_date', '').strip(),
            'remark': request.POST.get('remark', '').strip(),
        }

        if blocked_status:
            # ปิดที่ฝั่ง server ด้วย ไม่ใช่แค่ disable ใน HTML (disable แก้ได้จาก devtools)
            form_errors.append(
                f"สัญญานี้มีสถานะ \"{contract.get('Status_contract_Desc') or '-'}\" อยู่แล้ว "
                'จึงบันทึกยกเลิกสัญญาไม่ได้'
            )
        if form['termination_case'] not in TERMINATION_CASES:
            form_errors.append('กรุณาเลือกกรณีการยกเลิกสัญญา')
        if not form['contract_end_date']:
            form_errors.append('กรุณาระบุวันที่สิ้นสุดสัญญา')
        if form['termination_case'] == CASE_CANCEL_BEFORE_END and not form['notify_date']:
            form_errors.append('กรณียกเลิกสัญญาก่อนครบอายุ ต้องระบุวันที่แจ้งยกเลิกด้วย')

        if not form_errors:
            try:
                services.save_termination(
                    contract_id, None, form['termination_case'],
                    form['contract_end_date'], form['notify_date'] or None,
                    form['remark'] or None, DEFAULT_USER,
                )
                return redirect('termination_detail', contract_id=contract_id)
            except Exception as exc:
                form_errors.append(_sp_error_message(
                    exc, 'บันทึกข้อมูลยกเลิกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล'))

    header, periods = services.fetch_termination_detail(contract_id=contract_id)
    contract_meters = services.fetch_contract_meter_detail(contract_id=contract_id)

    # ติดธงมิเตอร์ซ้ำ -- ข้อมูลจริงมีมิเตอร์หลายตัว (Meter_id ต่างกัน) ที่อยู่พื้นที่ย่อยเดียวกัน
    # ประเภทเดียวกัน และเลขมิเตอร์เดียวกัน (เช่นสัญญา 226 มี Meter_id 1018 กับ 1042 เลข 9429518
    # ทั้งคู่) ถ้าไม่บอกไว้ ตารางจะดูเหมือนแสดงแถวซ้ำโดยไม่มีเหตุผล
    meter_groups = {}
    for row in contract_meters:
        key = (row.get('SubArea_id'), row.get('Meter_type_cd'), row.get('Meter_no'))
        meter_groups.setdefault(key, []).append(row)
    duplicate_meter_count = sum(len(g) - 1 for g in meter_groups.values() if len(g) > 1)
    for group in meter_groups.values():
        for row in group:
            row['is_duplicate'] = len(group) > 1

    # แปลงงวด YYYYMM (ค.ศ.) เป็นข้อความไทย พ.ศ. สำหรับแสดงผล -- ค่าที่เก็บใน DB ไม่เปลี่ยน
    for p in periods:
        p['period_label'] = _period_label(p.get('Installment_period'))
    if header:
        header['last_period_label'] = _period_label(header.get('Last_installment_period'))

    # นับงวดที่เลือกไว้ -- โชว้ "เลือกอยู่ x จาก y งวด" คู่กับปุ่มเลือก/ไม่เลือกทั้งหมด
    selected_count = sum(1 for p in periods if p.get('Is_selected'))

    # สถานะการผูกมิเตอร์กับสัญญา -- ใช้คุมปุ่ม "ปิดการตั้งหนี้มิเตอร์"
    meter_bindings = services.count_meter_bindings(contract_id)
    buffer_passed = _buffer_period_passed(header)

    # ประวัติรายการยกเลิกที่ถูกลบของสัญญานี้ -- ข้อมูลมีอยู่ใน Contract_termination_tr_log
    # แล้วแต่เดิมไม่มีที่ไหนเอามาแสดง ทำให้มองไม่เห็นว่าเคยมีรายการก่อนหน้าเป็นอะไร
    deleted_history = services.fetch_termination_history(contract_id)
    for row in deleted_history:
        row['last_period_label'] = _period_label(row.get('Last_installment_period'))

    # ยังไม่ได้บันทึกอะไร: เติม "วันที่สิ้นสุดสัญญา" จาก Contract_tr.End_contract ให้ล่วงหน้า
    # ยังแก้ได้ เพราะวันสิ้นสุดที่ใช้ยกเลิกอาจต่างจากในสัญญาเดิมโดยเจตนา
    # ทำเฉพาะ GET -- ถ้าเป็น POST ที่ error ต้องคงค่าที่ผู้ใช้พิมพ์มา ไม่เขียนทับ
    end_date_autofilled = False
    if request.method != 'POST' and not header and end_contract:
        form['contract_end_date'] = end_contract.strftime('%Y-%m-%d')
        end_date_autofilled = True

    # GET ปกติ: เติมค่าในฟอร์มจากข้อมูลที่บันทึกไว้ (ถ้ามี)
    # ถ้าเป็น POST ที่ error ให้คงค่าที่ผู้ใช้พิมพ์มาไว้ ไม่ย้อนกลับเป็นค่าใน DB
    if request.method != 'POST' and header:
        form = {
            # Termination_case ใน DB เป็น TINYINT (int) แต่คีย์ใน TERMINATION_CASES เป็น str
            # ต้อง cast เป็น str ไม่งั้นเทมเพลตเทียบไม่ตรง -> dropdown ไม่ preselect กรณีปัจจุบัน
            'termination_case': str(header.get('Termination_case') or ''),
            'contract_end_date': (header['Contract_end_date'].strftime('%Y-%m-%d')
                                  if header.get('Contract_end_date') else ''),
            'notify_date': (header['Notify_date'].strftime('%Y-%m-%d')
                            if header.get('Notify_date') else ''),
            'remark': header.get('Remark') or '',
        }

    context = {
        'contract_id': contract_id,
        'contract': contract,
        'blocked_status': blocked_status,
        'end_date_autofilled': end_date_autofilled,
        'end_date_is_past': end_contract_is_past,
        'end_date_missing': not end_contract,
        # ฟอร์มกรอกได้เฉพาะตอนยังไม่มีข้อมูลยกเลิก และสถานะสัญญายังไม่ถูกบล็อก
        'can_save': not header and not blocked_status,
        'header': header,
        'periods': periods,
        'selected_count': selected_count,
        'termination_cases': TERMINATION_CASES,
        'case_cancel_before_end': CASE_CANCEL_BEFORE_END,
        # ส่งไปให้ JS คำนวณ preview ในกล่องยืนยัน -- ส่งเป็นข้อมูลแทนการ hardcode ซ้ำในไฟล์ JS
        'thai_months': THAI_MONTHS,
        'case_buffer_months': CASE_BUFFER_MONTHS,
        'contract_meters': contract_meters,
        'duplicate_meter_count': duplicate_meter_count,
        'meter_bindings': meter_bindings,
        'buffer_passed': buffer_passed,
        'deleted_history': deleted_history,
        'default_user': DEFAULT_USER,
        'can_close_meters': bool(header) and buffer_passed and meter_bindings['active'] > 0,
        'form': form,
        # รวม 2 กองตอนส่งให้เทมเพลตแสดง -- แต่การตัดสินใจบันทึกใช้ form_errors เท่านั้น
        'errors': form_errors + notices,
        'flash_warning': flash_warning,
        'flash_success': flash_success,
        # ตัวกรองของหน้ารายการที่ส่งต่อมาทาง query string -- ใช้ทำลิงก์ breadcrumb กลับ
        # เอาเฉพาะคีย์ที่รู้จัก ไม่ส่งต่อทุกอย่างที่ติดมาใน URL
        'back_qs': urlencode({
            key: request.GET[key]
            for key in ('tab', 'scope', 'status', 'q', 'page')
            if request.GET.get(key)
        }),
    }
    return render(request, 'meters/termination_detail.html', context)


def _termination_id_or_none(contract_id):
    """หา Termination_id ของสัญญานี้ -- ยังไม่มีข้อมูลยกเลิก = ยังผูกงวดไม่ได้"""
    header, _periods = services.fetch_termination_detail(contract_id=contract_id)
    return header.get('Termination_id') if header else None


def termination_delete(request, contract_id):
    """
    ลบรายการยกเลิกสัญญา -- ทางแก้เมื่อบันทึกผิด (เลือก case ผิด / กรอกวันที่ผิด)

    sp_Contract_Termination_Save บันทึกได้ครั้งเดียวต่อสัญญาและไม่มี SP แก้ไข
    เดิมถ้ากรอกผิดต้องให้คนไปแก้ที่ฐานข้อมูล ตอนนี้ลบแล้วบันทึกใหม่ให้ถูกได้

    SP คืนสถานะสัญญากลับเป็นค่าก่อนยกเลิก (Prev_status_contract_id) ให้ด้วย
    ถ้าคืนไม่ได้ (แถวเก่าที่ไม่มีค่านั้น) จะส่งธงกลับมาให้เตือนผู้ใช้
    """
    if request.method != 'POST':
        return redirect('termination_detail', contract_id=contract_id)

    from django.urls import reverse
    detail_url = reverse('termination_detail', args=[contract_id])

    try:
        result = services.delete_termination(contract_id, DEFAULT_USER)
    except Exception as exc:
        request.session['termination_flash_error'] = _sp_error_message(
            exc, 'ลบรายการยกเลิกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล')
        return redirect(detail_url)

    if result and not result.get('Status_restored'):
        request.session['termination_flash_warning'] = (
            'ลบรายการยกเลิกแล้ว แต่ระบบคืนสถานะสัญญาให้อัตโนมัติไม่ได้ '
            'เพราะรายการนี้ไม่ได้บันทึกสถานะเดิมไว้ -- กรุณาตรวจสอบสถานะสัญญาด้วยตนเอง'
        )
    else:
        request.session['termination_flash_success'] = 'ลบรายการยกเลิกแล้ว คืนสถานะสัญญากลับเป็นค่าเดิมเรียบร้อย'

    return redirect(detail_url)


LOG_PER_PAGE = 30


def termination_log(request):
    """
    หน้าประวัติการยกเลิกสัญญาทั้งระบบ -- ใครบันทึก ใครลบ เมื่อไหร่

    ข้อมูลถูกเก็บไว้แล้วใน Contract_termination_tr (UserEntry/DateEntry) และ
    Contract_termination_tr_log (UserDelete/DateDelete) แต่เดิมไม่มีหน้าไหนเอามาแสดง

    ข้อจำกัดที่ต้องรู้: ตอนนี้ระบบยังไม่มีล็อกอิน ชื่อผู้ทำรายการจึงเป็นค่าคงที่
    DEFAULT_USER ทุกแถว -- log บอกได้ว่า "เกิดอะไรขึ้นเมื่อไหร่" แต่ยังบอกไม่ได้ว่า
    "ใครทำ" จนกว่าจะผูกตัวตนจากระบบ CMS (K2) เข้ามา เทมเพลตเขียนกำกับไว้ให้ผู้ใช้รู้
    """
    search = request.GET.get('q', '').strip()
    event = request.GET.get('event', services.LOG_EVENT_ALL if hasattr(services, 'LOG_EVENT_ALL') else 'all')
    valid_events = dict(services.TERMINATION_LOG_EVENTS)
    if event not in valid_events:
        event = 'all'

    rows = services.fetch_termination_log(search)

    counts = {'all': len(rows)}
    for key, _label in services.TERMINATION_LOG_EVENTS:
        if key != 'all':
            counts[key] = sum(1 for r in rows if r['Event_type'] == key)

    visible = rows if event == 'all' else [r for r in rows if r['Event_type'] == event]

    for r in visible:
        r['period_label'] = _period_label(r.get('Last_installment_period'))

    paginator = Paginator(visible, LOG_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    events = [
        {'key': key, 'label': label, 'count': counts.get(key, 0), 'is_active': key == event}
        for key, label in services.TERMINATION_LOG_EVENTS
    ]

    context = {
        'page_obj': page_obj,
        'rows': page_obj.object_list,
        'total_visible': len(visible),
        'events': events,
        'active_event': event,
        'search': search,
        'default_user': DEFAULT_USER,
    }
    return render(request, 'meters/termination_log.html', context)


def _buffer_period_passed(header, today=None):
    """
    พ้นงวดสุดท้ายที่จัดการได้แล้วหรือยัง (เทียบ Last_installment_period รูปแบบ YYYYMM ค.ศ.)

    ใช้คุมว่าปุ่ม "ปิดการตั้งหนี้มิเตอร์" กดได้เมื่อไหร่ -- ปิดก่อนพ้นงวดผ่อนผันจะทำให้
    สัญญาหลุดจากไฟล์ดาวน์โหลด แล้วงวดผ่อนผัน (1-2 เดือนตาม case) หายไปจากการตั้งหนี้
    """
    if not header:
        return False
    text = str(header.get('Last_installment_period') or '').strip()
    if len(text) != 6 or not text.isdigit():
        return False
    today = today or datetime.date.today()
    return f'{today.year}{today.month:02d}' > text


def termination_close_meters(request, contract_id):
    """
    ปิดการตั้งหนี้มิเตอร์ของสัญญาที่ยกเลิกแล้ว (Contract_meter_tr.UseOrNot = 0)

    ไม่แตะทะเบียนมิเตอร์ (Contract_meter_ms) -- มิเตอร์เป็นของกายภาพติดกับพื้นที่
    ผู้เช่ารายใหม่ยังต้องใช้ตัวเดิม ปิดแค่การผูกเข้ากับสัญญาที่ยกเลิกไปแล้ว

    กดได้เฉพาะเมื่อพ้นงวดสุดท้ายแล้ว -- เช็คทั้งที่นี่และที่เทมเพลต
    (เทมเพลตซ่อนปุ่ม ที่นี่กันการดัดแปลง request)
    """
    if request.method != 'POST':
        return redirect('termination_detail', contract_id=contract_id)

    from django.urls import reverse
    detail_url = reverse('termination_detail', args=[contract_id])

    header, _periods = services.fetch_termination_detail(contract_id=contract_id)
    if not header:
        request.session['termination_flash_error'] = (
            'สัญญานี้ยังไม่มีรายการยกเลิก จึงปิดการตั้งหนี้มิเตอร์ไม่ได้')
        return redirect(detail_url)

    if not _buffer_period_passed(header):
        request.session['termination_flash_error'] = (
            'ยังไม่พ้นงวดสุดท้ายที่จัดการได้ จึงยังปิดการตั้งหนี้มิเตอร์ไม่ได้ '
            '-- ถ้าปิดตอนนี้งวดผ่อนผันจะหายไปจากการตั้งหนี้'
        )
        return redirect(detail_url)

    try:
        closed = services.close_meter_billing(contract_id, DEFAULT_USER)
    except Exception as exc:
        request.session['termination_flash_error'] = _sp_error_message(
            exc, 'ปิดการตั้งหนี้มิเตอร์ไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล')
        return redirect(detail_url)

    request.session['termination_flash_success'] = (
        f'ปิดการตั้งหนี้มิเตอร์แล้ว {closed} รายการ -- ทะเบียนมิเตอร์ยังอยู่ ใช้กับสัญญาใหม่ได้'
    )
    return redirect(detail_url)


def termination_select_all_installments(request, contract_id):
    """
    ติ๊ก/ยกเลิกงวดทั้งหมดในคราวเดียว -- เดิมต้องกดทีละงวด (1 reload ต่องวด)

    ?is_selected=1 เลือกทั้งหมด / 0 ไม่เลือกทั้งหมด
    """
    if request.method != 'POST':
        return redirect('termination_detail', contract_id=contract_id)

    termination_id = _termination_id_or_none(contract_id)
    if not termination_id:
        return redirect('termination_detail', contract_id=contract_id)

    is_selected = request.POST.get('is_selected') == '1'
    try:
        services.set_all_installment_selections(termination_id, is_selected, DEFAULT_USER)
    except Exception:
        from django.urls import reverse
        return redirect(f"{reverse('termination_detail', args=[contract_id])}?toggle_error=1")

    return redirect('termination_detail', contract_id=contract_id)


def termination_toggle_installment(request, contract_id, period):
    """
    ติ๊ก/ยกเลิกงวดหนึ่งงวด -- ต้องมี Termination record อยู่แล้ว (บันทึกข้อมูลยกเลิกหลักก่อน
    ถึงจะมี Termination_id ให้ผูกงวดได้) ถ้ายังไม่มี ส่งกลับไปหน้า detail เฉยๆ

    ครอบ try/except เพราะ sp_Contract_Termination_SetInstallmentSelection จะ RAISERROR
    ถ้าไม่พบงวดนั้นในรายการ -- ส่งสัญญาณกลับไปทาง query string ให้หน้า detail แสดงข้อความ
    """
    if request.method != 'POST':
        return redirect('termination_detail', contract_id=contract_id)

    termination_id = _termination_id_or_none(contract_id)
    if not termination_id:
        return redirect('termination_detail', contract_id=contract_id)

    is_selected = request.POST.get('is_selected') == '1'
    try:
        services.set_installment_selection(termination_id, period, is_selected, DEFAULT_USER)
    except Exception:
        from django.urls import reverse
        return redirect(f"{reverse('termination_detail', args=[contract_id])}?toggle_error=1")

    return redirect('termination_detail', contract_id=contract_id)
