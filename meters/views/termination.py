# meters/views/termination.py
import datetime
import re
from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import render, redirect

from .. import services
from ..utils import (
    THAI_MONTHS, expired_ago_label, parse_iso_date, period_label, thai_date, thai_datetime,
)

from ..services.access import fetch_user_access

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
    contract['start_contract_label'] = thai_date(contract.get('Start_contract'))
    contract['end_contract_label'] = thai_date(contract.get('End_contract'))

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
    contract['expired_ago_label'] = expired_ago_label(end_contract)

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
        elif not parse_iso_date(form['contract_end_date']):
            form_errors.append('วันที่สิ้นสุดสัญญาไม่ถูกต้อง')
        if form['termination_case'] == CASE_CANCEL_BEFORE_END and not form['notify_date']:
            form_errors.append('กรณียกเลิกสัญญาก่อนครบอายุ ต้องระบุวันที่แจ้งยกเลิกด้วย')
        elif form['notify_date'] and not parse_iso_date(form['notify_date']):
            form_errors.append('วันที่แจ้งยกเลิกไม่ถูกต้อง')

        if not form_errors:
            try:
                services.save_termination(
                    contract_id, None, form['termination_case'],
                    form['contract_end_date'], form['notify_date'] or None,
                    form['remark'] or None, request.user.get_username(),
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
        p['period_label'] = period_label(p.get('Installment_period'))
    if header:
        header['last_period_label'] = period_label(header.get('Last_installment_period'))
        header['notify_date_label'] = thai_date(header.get('Notify_date'))
        header['date_entry_label'] = thai_datetime(header.get('DateEntry'))

    # นับงวดที่เลือกไว้ -- โชว้ "เลือกอยู่ x จาก y งวด" คู่กับปุ่มเลือก/ไม่เลือกทั้งหมด
    selected_count = sum(1 for p in periods if p.get('Is_selected'))

    # สถานะการผูกมิเตอร์กับสัญญา -- ใช้คุมปุ่ม "ปิดการตั้งหนี้มิเตอร์"
    meter_bindings = services.count_meter_bindings(contract_id)
    buffer_passed = _buffer_period_passed(header)

    # ประวัติรายการยกเลิกที่ถูกลบของสัญญานี้ -- ข้อมูลมีอยู่ใน Contract_termination_tr_log
    # แล้วแต่เดิมไม่มีที่ไหนเอามาแสดง ทำให้มองไม่เห็นว่าเคยมีรายการก่อนหน้าเป็นอะไร
    deleted_history = services.fetch_termination_history(contract_id)
    for row in deleted_history:
        row['last_period_label'] = period_label(row.get('Last_installment_period'))
        row['end_date_label'] = thai_date(row.get('Contract_end_date'))
        row['entry_label'] = thai_datetime(row.get('DateEntry'))
        row['delete_label'] = thai_datetime(row.get('DateDelete'))

    # แปลง Buasri ID เป็นชื่อ-สกุลจริงเพื่อแสดงผล (ค่าในฐานข้อมูลยังเป็น ID เดิม)
    # ไม่พบชื่อหรือดึงไม่ได้ -> แสดง ID เดิมแทน ไม่ให้หน้าล่ม
    ids = {header.get('UserEntry')} if header else set()
    for row in deleted_history:
        ids.update((row.get('UserEntry'), row.get('UserDelete')))

    names = {}
    for uid in ids:
        if not uid:
            continue
        try:
            info = fetch_user_access(uid)
        except Exception:
            info = None
        names[uid] = info['display_name'] if info else uid

    if header:
        header['UserEntry_name'] = names.get(header.get('UserEntry'))
    for row in deleted_history:
        row['UserEntry_name'] = names.get(row.get('UserEntry'))
        row['UserDelete_name'] = names.get(row.get('UserDelete'))

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
        'default_user': request.user.get_username(),
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
        result = services.delete_termination(contract_id, request.user.get_username())
    except Exception as exc:
        request.session['termination_flash_error'] = _sp_error_message(
            exc, 'ลบรายการยกเลิกไม่สำเร็จ -- เกิดข้อผิดพลาดจากระบบฐานข้อมูล')
        return redirect(detail_url)

    if result is None:
        request.session['termination_flash_warning'] = (
            'ส่งคำสั่งลบรายการยกเลิกแล้ว แต่ระบบไม่ได้รับผลลัพธ์กลับมา '
            '-- กรุณาตรวจสอบรายการและสถานะสัญญาด้วยตนเอง'
        )
    elif not result.get('Status_restored'):
        request.session['termination_flash_warning'] = (
            'ลบรายการยกเลิกแล้ว แต่ระบบคืนสถานะสัญญาให้อัตโนมัติไม่ได้ '
            'เพราะรายการนี้ไม่ได้บันทึกสถานะเดิมไว้ -- กรุณาตรวจสอบสถานะสัญญาด้วยตนเอง'
        )
    else:
        request.session['termination_flash_success'] = 'ลบรายการยกเลิกแล้ว คืนสถานะสัญญากลับเป็นค่าเดิมเรียบร้อย'

    return redirect(detail_url)


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
        closed = services.close_meter_billing(contract_id, request.user.get_username())
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
        services.set_all_installment_selections(
            termination_id, is_selected, request.user.get_username()
        )
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
        services.set_installment_selection(
            termination_id, period, is_selected, request.user.get_username()
        )
    except Exception:
        from django.urls import reverse
        return redirect(f"{reverse('termination_detail', args=[contract_id])}?toggle_error=1")

    return redirect('termination_detail', contract_id=contract_id)