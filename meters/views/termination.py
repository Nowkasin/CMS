# meters/views/termination.py
import re

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


def termination_search(request):
    """
    หน้าแรก: กรอกรหัสสัญญา (หรือชื่อลูกค้า) เพื่อค้นหาก่อนเข้าไปหน้ายกเลิกจริง

    ผลค้นหาโชว์สถานะสัญญาและธง "ยกเลิกไปแล้ว" ด้วย -- เดิม service ดึง
    Status_contract_id มาแล้วแต่เทมเพลตไม่ได้ใช้ ผู้ใช้จึงเลือกสัญญาที่ปิด/ยกเลิก
    ไปแล้วเข้าไป แล้วเพิ่งไปเจอทางตันที่หน้าถัดไป
    """
    context = {
        'error': None,
        'contract_code': '',
        'matches': None,
        'truncated': False,
        'search_limit': services.SEARCH_RESULT_LIMIT,
    }

    if request.method == 'POST':
        contract_code = request.POST.get('contract_code', '').strip()
        context['contract_code'] = contract_code
        if not contract_code:
            context['error'] = 'กรุณากรอกรหัสสัญญาหรือชื่อลูกค้า'
        else:
            matches = services.find_contract_for_termination(contract_code)

            # service ดึงเกินลิมิตมา 1 แถวเพื่อให้รู้ว่ายังมีอีก -- ตัดแถวเกินออกแล้วตั้งธงเตือน
            if len(matches) > services.SEARCH_RESULT_LIMIT:
                matches = matches[:services.SEARCH_RESULT_LIMIT]
                context['truncated'] = True

            for m in matches:
                m['is_blocked'] = (
                    m.get('Status_contract_id') in services.BLOCKED_CONTRACT_STATUSES
                    or bool(m.get('Has_termination'))
                )

            if not matches:
                context['error'] = f"ไม่พบรหัสสัญญาหรือชื่อลูกค้าที่ตรงกับ '{contract_code}'"
            elif len(matches) == 1 and not context['truncated']:
                return redirect('termination_detail', contract_id=matches[0]['Contract_id'])
            else:
                context['matches'] = matches

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

    errors = []

    # ข้อความ error จากการติ๊กงวด -- ส่งต่อมาทาง query string เพราะ toggle redirect กลับมาที่นี่
    if request.GET.get('toggle_error'):
        errors.append('เปลี่ยนสถานะงวดไม่สำเร็จ -- กรุณาลองใหม่อีกครั้ง')

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
            errors.append(
                f"สัญญานี้มีสถานะ \"{contract.get('Status_contract_Desc') or '-'}\" อยู่แล้ว "
                'จึงบันทึกยกเลิกสัญญาไม่ได้'
            )
        if form['termination_case'] not in TERMINATION_CASES:
            errors.append('กรุณาเลือกกรณีการยกเลิกสัญญา')
        if not form['contract_end_date']:
            errors.append('กรุณาระบุวันที่สิ้นสุดสัญญา')
        if form['termination_case'] == CASE_CANCEL_BEFORE_END and not form['notify_date']:
            errors.append('กรณียกเลิกสัญญาก่อนครบอายุ ต้องระบุวันที่แจ้งยกเลิกด้วย')

        if not errors:
            try:
                services.save_termination(
                    contract_id, None, form['termination_case'],
                    form['contract_end_date'], form['notify_date'] or None,
                    form['remark'] or None, DEFAULT_USER,
                )
                return redirect('termination_detail', contract_id=contract_id)
            except Exception as exc:
                errors.append(_sp_error_message(
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
        'form': form,
        'errors': errors,
    }
    return render(request, 'meters/termination_detail.html', context)


def _termination_id_or_none(contract_id):
    """หา Termination_id ของสัญญานี้ -- ยังไม่มีข้อมูลยกเลิก = ยังผูกงวดไม่ได้"""
    header, _periods = services.fetch_termination_detail(contract_id=contract_id)
    return header.get('Termination_id') if header else None


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
