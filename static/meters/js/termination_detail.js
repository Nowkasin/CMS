// หน้า termination_detail.html -- modal ยืนยันก่อนบันทึกการยกเลิกสัญญา
// กล่องยืนยันสรุปสิ่งที่จะเกิดขึ้นจากค่าที่กรอกไว้ด้วย เพราะบันทึกแล้วแก้เองไม่ได้
(function () {
  const openBtn = document.getElementById('openConfirmBtn');
  const modal = document.getElementById('confirmModal');
  const backdrop = document.getElementById('confirmBackdrop');
  const box = document.getElementById('confirmBox');
  const btnNo = document.getElementById('confirmNo');
  const btnYes = document.getElementById('confirmYes');
  const form = document.getElementById('terminationForm');

  const summaryBox = document.getElementById('confirmSummary');
  const missingBox = document.getElementById('confirmMissing');
  const questionEl = document.getElementById('confirmQuestion');

  if (!openBtn || !modal || !form) return;

  // ค่าคงที่ส่งมาจากเทมเพลตผ่าน json_script -- ไม่ hardcode ซ้ำที่นี่
  function readJson(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return fallback;
    }
  }
  const THAI_MONTHS = readJson('thaiMonths', []);
  const CASE_BUFFER_MONTHS = readJson('caseBufferMonths', {});

  const caseSelect = document.getElementById('terminationCase');
  const endDateInput = form.querySelector('[name="contract_end_date"]');
  const notifyDateInput = form.querySelector('[name="notify_date"]');

  // รหัส case "ยกเลิกก่อนครบอายุ" -- ตัวเดียวที่บังคับกรอกวันที่แจ้งยกเลิก
  const CASE_CANCEL_BEFORE_END = form.dataset.caseCancelBeforeEnd || '1';

  // 'ยกเลิกสัญญาก่อนครบอายุสัญญา (จัดการต่อได้อีก 2 เดือน)' -> ตัดวงเล็บท้ายออกให้อ่านสั้นลง
  function caseLabel() {
    if (!caseSelect || !caseSelect.value) return '';
    const opt = caseSelect.options[caseSelect.selectedIndex];
    return opt ? opt.textContent.trim() : '';
  }

  // แปลง 'YYYY-MM-DD' เป็น {year, month} โดยอ่านจากสตริงตรงๆ
  // ไม่ใช้ new Date() เพราะ parse แบบ UTC แล้วอาจเพี้ยนไปหนึ่งวันตาม timezone
  function parseDateParts(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || '').trim());
    if (!m) return null;
    const year = Number(m[1]);
    const month = Number(m[2]);
    const day = Number(m[3]);
    if (month < 1 || month > 12 || day < 1 || day > 31) return null;
    return { year: year, month: month, day: day };
  }

  // 'YYYY-MM-DD' -> '15 ธันวาคม 2569' (แสดงเป็น พ.ศ. เหมือนที่อื่นในระบบ)
  function thaiDate(value) {
    const d = parseDateParts(value);
    if (!d) return null;
    return d.day + ' ' + (THAI_MONTHS[d.month - 1] || d.month) + ' ' + (d.year + 543);
  }

  // งวดสุดท้าย = เดือนของวันสิ้นสุดสัญญา + จำนวนเดือนผ่อนผัน
  // คำนวณซ้ำกับ sp_Contract_Termination_Save เพื่อ "แสดง preview" เท่านั้น
  // ค่าที่บันทึกจริงมาจาก SP -- ถ้าสูตรใน SP เปลี่ยน ต้องมาแก้ที่นี่ด้วย
  function lastPeriodLabel(endValue, bufferMonths) {
    const d = parseDateParts(endValue);
    if (!d || typeof bufferMonths !== 'number') return null;
    const zeroBased = d.month - 1 + bufferMonths;
    const year = d.year + Math.floor(zeroBased / 12);
    const month = (zeroBased % 12) + 1;
    return (THAI_MONTHS[month - 1] || month) + ' ' + (year + 543);
  }

  function row(label, value) {
    return (
      '<div class="flex justify-between gap-3">' +
      '<span class="text-gray-500 shrink-0">' + label + '</span>' +
      '<span class="text-gray-800 font-medium text-right">' + value + '</span>' +
      '</div>'
    );
  }

  // เช็กฝั่ง client เพื่อไม่ให้กดยืนยันไปแล้วเจอ error -- ฝั่ง server ยังเช็กซ้ำอยู่ดี
  function missingFields() {
    const missing = [];
    if (!caseSelect || !caseSelect.value) missing.push('กรณีการยกเลิก');
    if (!endDateInput || !parseDateParts(endDateInput.value)) missing.push('วันที่สิ้นสุดสัญญา');
    // วันที่แจ้งยกเลิกบังคับเฉพาะกรณียกเลิกก่อนครบอายุ (ตรงกับเงื่อนไขใน SP และใน view)
    // ค่า case อ่านจาก data attribute ไม่ hardcode '1' ไว้ในนี้
    if (caseSelect && caseSelect.value === CASE_CANCEL_BEFORE_END &&
        (!notifyDateInput || !parseDateParts(notifyDateInput.value))) {
      missing.push('วันที่แจ้งยกเลิก');
    }
    return missing;
  }

  function buildSummary() {
    const missing = missingFields();

    if (missing.length) {
      if (summaryBox) summaryBox.innerHTML = '';
      if (missingBox) {
        missingBox.textContent = 'ยังกรอกไม่ครบ: ' + missing.join(', ');
        missingBox.classList.remove('hidden');
      }
      if (questionEl) questionEl.textContent = 'กรุณากรอกข้อมูลให้ครบก่อนบันทึก';
      if (btnYes) btnYes.disabled = true;
      return;
    }

    if (missingBox) missingBox.classList.add('hidden');
    if (btnYes) btnYes.disabled = false;
    if (questionEl) {
      questionEl.textContent = 'บันทึกแล้วจะแก้ไขเองไม่ได้ ต้องการดำเนินการต่อหรือไม่?';
    }

    const buffer = CASE_BUFFER_MONTHS[caseSelect.value];
    const parts = [row('กรณี', caseLabel())];
    parts.push(row('วันที่สิ้นสุดสัญญา', thaiDate(endDateInput.value) || '—'));
    if (notifyDateInput && parseDateParts(notifyDateInput.value)) {
      parts.push(row('วันที่แจ้งยกเลิก', thaiDate(notifyDateInput.value)));
    }
    if (typeof buffer === 'number') {
      parts.push(row('จัดการต่อได้อีก', buffer + ' เดือน'));
      const last = lastPeriodLabel(endDateInput.value, buffer);
      if (last) parts.push(row('งวดสุดท้ายที่จัดการได้', last));
    }
    if (summaryBox) summaryBox.innerHTML = parts.join('');
  }

  function openModal() {
    buildSummary();
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    requestAnimationFrame(() => {
      backdrop.classList.remove('opacity-0');
      backdrop.classList.add('opacity-100');
      box.classList.remove('opacity-0', 'scale-90');
      box.classList.add('opacity-100', 'scale-100');
    });
  }

  function closeModal() {
    backdrop.classList.remove('opacity-100');
    backdrop.classList.add('opacity-0');
    box.classList.remove('opacity-100', 'scale-100');
    box.classList.add('opacity-0', 'scale-90');
    setTimeout(() => {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }, 200);
  }

  openBtn.addEventListener('click', openModal);
  btnNo.addEventListener('click', closeModal);
  backdrop.addEventListener('click', closeModal);
  btnYes.addEventListener('click', () => {
    if (btnYes.disabled) return;
    closeModal();
    form.submit();
  });
})();
