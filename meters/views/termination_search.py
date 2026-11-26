# meters/views/termination_search.py
"""
หน้ารายการสัญญาสำหรับงานยกเลิกสัญญา (แท็บ / ขอบเขต / ค้นหา / แบ่งหน้า)
หน้ารายละเอียดและการกระทำกับสัญญา (บันทึก/ลบ/ติ๊กงวด/ปิดการตั้งหนี้) อยู่ที่ termination.py
"""
import datetime

from django.core.paginator import Paginator
from django.shortcuts import render

from .. import services
from ..utils import expired_ago_label, period_label, thai_date


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
    row['end_contract_label'] = thai_date(end)
    row['expired_ago_label'] = expired_ago_label(end, today)
    row['notify_date_label'] = thai_date(row.get('Notify_date'))
    row['grace_until_label'] = period_label(row.get('Last_installment_period'))

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
