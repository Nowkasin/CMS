# meters/views/termination.py
from django.shortcuts import render, redirect

from .. import services

DEFAULT_USER = 'web_upload'

# TODO: ยืนยันค่า termination_case จริงที่ SP คาดหวัง -- เดาไว้ตามบันทึกการประชุม
TERMINATION_CASES = {
    '1': 'ยกเลิกสัญญาก่อนครบอายุสัญญา (จัดการต่อได้อีก 2 เดือน)',
    '2': 'สิ้นสุดสัญญาและไม่ต่อสัญญา (จัดการต่อได้อีก 1 เดือน)',
}


def termination_search(request):
    """หน้าแรก: กรอกรหัสสัญญา (หรือชื่อลูกค้า) เพื่อค้นหาก่อนเข้าไปหน้ายกเลิกจริง"""
    context = {'error': None, 'contract_code': '', 'matches': None}

    if request.method == 'POST':
        contract_code = request.POST.get('contract_code', '').strip()
        context['contract_code'] = contract_code
        if not contract_code:
            context['error'] = 'กรุณากรอกรหัสสัญญาหรือชื่อลูกค้า'
        else:
            matches = services.find_contract_for_termination(contract_code)
            if not matches:
                context['error'] = f"ไม่พบรหัสสัญญาหรือชื่อลูกค้าที่ตรงกับ '{contract_code}'"
            elif len(matches) == 1:
                return redirect('termination_detail', contract_id=matches[0]['Contract_id'])
            else:
                context['matches'] = matches

    return render(request, 'meters/termination_search.html', context)


def termination_detail(request, contract_id):
    """
    โชว์ข้อมูลยกเลิกสัญญา (ถ้ามีอยู่แล้ว) + รายการงวดทั้งหมดของสัญญานี้
    + รายละเอียดสัญญา/มิเตอร์ (จาก fetch_contract_meter_detail เดิมที่ใช้กับหน้ามิเตอร์)
    POST ที่นี่ = บันทึก/อัปเดตข้อมูลยกเลิก (ไม่ใช่ติ๊กงวด -- งวดแยกไปที่ termination_toggle_installment)
    """
    error = None

    if request.method == 'POST':
        termination_case = request.POST.get('termination_case')
        contract_end_date = request.POST.get('contract_end_date') or None
        notify_date = request.POST.get('notify_date') or None
        remark = request.POST.get('remark', '').strip() or None

        if not termination_case:
            error = 'กรุณาเลือกกรณีการยกเลิกสัญญา'
        else:
            services.save_termination(
                contract_id, None, termination_case, contract_end_date, notify_date, remark, DEFAULT_USER,
            )
            return redirect('termination_detail', contract_id=contract_id)

    header, periods = services.fetch_termination_detail(contract_id=contract_id)
    contract_meters = services.fetch_contract_meter_detail(contract_id=contract_id)

    context = {
        'contract_id': contract_id,
        'header': header,
        'periods': periods,
        'termination_cases': TERMINATION_CASES,
        'contract_meters': contract_meters,
        'error': error,
    }
    return render(request, 'meters/termination_detail.html', context)


def termination_toggle_installment(request, contract_id, period):
    """
    ติ๊ก/ยกเลิกงวดหนึ่งงวด -- ต้องมี Termination record อยู่แล้ว (บันทึกข้อมูลยกเลิกหลักก่อน
    ถึงจะมี Termination_id ให้ผูกงวดได้) ถ้ายังไม่มี ส่งกลับไปหน้า detail เฉยๆ
    """
    if request.method != 'POST':
        return redirect('termination_detail', contract_id=contract_id)

    header, _periods = services.fetch_termination_detail(contract_id=contract_id)
    termination_id = header.get('Termination_id') if header else None
    if not termination_id:
        return redirect('termination_detail', contract_id=contract_id)

    is_selected = request.POST.get('is_selected') == '1'
    services.set_installment_selection(termination_id, period, is_selected, DEFAULT_USER)
    return redirect('termination_detail', contract_id=contract_id)