// ยืนยันก่อนบันทึก -- ใช้ร่วมกันทุกฟอร์มที่เขียนข้อมูลลงฐานข้อมูล
//
// ปัญหาที่แก้: ฟอร์มที่มีช่อง <input> บรรทัดเดียว + ปุ่ม submit จะถูก "implicit submission"
// ของ HTML ส่งทันทีเมื่อกด Enter ในช่องใดก็ได้ ผู้ใช้เผลอกด Enter ครั้งเดียว
// ข้อมูลถูกเขียนลงฐานข้อมูลไปแล้วโดยไม่มีจังหวะให้ทบทวน
//
// ป้องกัน 2 ชั้น:
//   ชั้นที่ 1  กด Enter ในฟอร์มไม่ส่งฟอร์มอีกต่อไป (ยกเว้นใน <textarea> ที่ Enter = ขึ้นบรรทัดใหม่
//             และยกเว้นตอนโฟกัสอยู่ที่ปุ่มเอง ซึ่งถือว่าผู้ใช้เจตนากดปุ่มนั้นจริง)
//   ชั้นที่ 2  กดปุ่มบันทึกแล้วขึ้นกล่องยืนยันพร้อมสรุปค่าที่จะบันทึก ต้องกด "ยืนยัน" อีกครั้ง
//             จึงจะส่งจริง ปุ่มที่ถูกโฟกัสตอนเปิดกล่องคือ "ยกเลิก" ไม่ใช่ "ยืนยัน"
//             เพื่อให้การเผลอกด Enter ซ้ำกลายเป็นการยกเลิก ไม่ใช่การยืนยัน
//
// วิธีใช้ในเทมเพลต (ไม่ต้องเขียน JS เพิ่มต่อหน้า):
//   <form method="post" data-confirm-submit
//         data-confirm-title="ยืนยันการบันทึก"
//         data-confirm-message="ข้อความอธิบายผลของการบันทึก">
//     <input name="x" data-confirm-field="ป้ายชื่อที่จะโชว์ในกล่องยืนยัน">
//
// ช่องที่ติด data-confirm-field จะถูกเอามาสรุปในกล่องยืนยันให้อ่านทบทวนก่อนกดจริง
//
// หมายเหตุ: การเรียก form.submit() ด้วย JS ไม่ยิง event 'submit' ปุ่มที่ทำงานแบบนั้นอยู่แล้ว
// (เช่น "ปิดใช้งาน" / "เปิดใช้งาน" ใน meter_form.js, phase_form.js ที่มีกล่องยืนยันของตัวเอง)
// จึงไม่ถูกดักซ้ำและไม่ขึ้นกล่องยืนยันสองชั้น
(function () {
  const forms = document.querySelectorAll('form[data-confirm-submit]');
  if (!forms.length) return;

  const modal = document.getElementById('submitConfirmModal');
  const backdrop = document.getElementById('submitConfirmBackdrop');
  const box = document.getElementById('submitConfirmBox');
  const titleEl = document.getElementById('submitConfirmTitle');
  const msgEl = document.getElementById('submitConfirmMessage');
  const fieldsEl = document.getElementById('submitConfirmFields');
  const btnNo = document.getElementById('submitConfirmNo');
  const btnYes = document.getElementById('submitConfirmYes');

  // ถ้า base.html ไม่มีกล่องยืนยัน (เช่นเทมเพลตที่ไม่ได้ extends base) ก็ยังต้องกัน Enter ให้ได้
  const hasModal = !!(modal && backdrop && box && btnNo && btnYes);

  let pendingForm = null;
  let lastTrigger = null;   // ปุ่ม submit ที่ถูกกดล่าสุด -- ใช้คืนโฟกัสและเก็บ name/value

  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

  /* อ่านค่าที่ผู้ใช้กรอกไว้ ให้ออกมาเป็นข้อความที่คนอ่านรู้เรื่อง
     ไม่ใช่ค่าดิบในฟอร์ม (เช่น select ต้องโชว์ข้อความของ option ไม่ใช่ value) */
  function readableValue(el) {
    if (el.tagName === 'SELECT') {
      const opt = el.options[el.selectedIndex];
      return opt ? norm(opt.textContent) : '';
    }
    if (el.type === 'checkbox') return el.checked ? 'ใช่' : 'ไม่';
    if (el.type === 'radio') {
      const checked = el.form ? el.form.querySelector(`input[name="${el.name}"]:checked`) : null;
      return checked ? norm(checked.value) : '';
    }
    return norm(el.value);
  }

  function buildSummary(form) {
    if (!fieldsEl) return;
    fieldsEl.textContent = '';

    const fields = form.querySelectorAll('[data-confirm-field]');
    if (!fields.length) {
      fieldsEl.classList.add('hidden');
      return;
    }

    fields.forEach((el) => {
      // เกณฑ์เดียวคือ disabled -- ช่องที่ disabled จะไม่ถูกส่งไปกับฟอร์ม จึงไม่ต้องโชว์
      // ไม่เช็กว่ามองเห็นบนจอหรือไม่ เพราะช่องที่ซ่อนด้วย CSS ยังถูกส่งไปจริง
      // (เช่น <select> พื้นที่ย่อยในหน้ามิเตอร์ ที่ถูกซ่อนแล้วแทนด้วย combobox
      //  แต่ยังเป็น form control ตัวจริงที่ถือค่าไว้) ถ้าข้ามไปจะสรุปไม่ครบ
      if (el.disabled) return;

      const row = document.createElement('div');
      row.className = 'flex items-start justify-between gap-3 py-1.5';

      const label = document.createElement('span');
      label.className = 'text-xs text-gray-500 shrink-0';
      label.textContent = el.dataset.confirmField;

      const value = document.createElement('span');
      const raw = readableValue(el);
      value.className = raw
        ? 'text-xs font-medium text-gray-900 text-right break-words'
        : 'text-xs text-gray-400 text-right';
      value.textContent = raw || '(ไม่ได้กรอก)';

      row.appendChild(label);
      row.appendChild(value);
      fieldsEl.appendChild(row);
    });

    fieldsEl.classList.toggle('hidden', !fieldsEl.children.length);
  }

  function openModal(form) {
    pendingForm = form;

    if (titleEl) titleEl.textContent = form.dataset.confirmTitle || 'ยืนยันการบันทึก';
    if (msgEl) {
      msgEl.textContent = form.dataset.confirmMessage
        || 'ข้อมูลนี้จะถูกบันทึกลงฐานข้อมูลทันที ต้องการดำเนินการต่อหรือไม่?';
    }
    if (btnYes) btnYes.textContent = form.dataset.confirmYes || 'ยืนยันบันทึก';
    buildSummary(form);

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // โฟกัสที่ "ยกเลิก" ไม่ใช่ "ยืนยัน" -- เผลอกด Enter ซ้ำจะได้เป็นการยกเลิก
    // ทำแบบ synchronous ตรงนี้ ไม่รอ requestAnimationFrame เพราะ rAF เป็น async
    // ถ้าผู้ใช้กด Enter รวดเร็วในช่วงก่อน frame ถัดไป โฟกัสจะยังอยู่ที่ช่องกรอกเดิม
    // (กล่องถูกถอด .hidden ไปแล้วบรรทัดบน ปุ่มจึงรับโฟกัสได้ ไม่ต้องรอ transition จบ)
    btnNo.focus();

    requestAnimationFrame(() => {
      backdrop.classList.remove('opacity-0');
      backdrop.classList.add('opacity-100');
      box.classList.remove('opacity-0', 'scale-90');
      box.classList.add('opacity-100', 'scale-100');
    });
  }

  function closeModal() {
    pendingForm = null;
    backdrop.classList.remove('opacity-100');
    backdrop.classList.add('opacity-0');
    box.classList.remove('opacity-100', 'scale-100');
    box.classList.add('opacity-0', 'scale-90');
    setTimeout(() => {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }, 200);
    if (lastTrigger && lastTrigger.focus) lastTrigger.focus();
  }

  const isOpen = () => hasModal && !modal.classList.contains('hidden');

  forms.forEach((form) => {
    /* ---------- ชั้นที่ 1: Enter ไม่ส่งฟอร์ม ---------- */
    form.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      // ถ้ามีตัวอื่นจัดการ Enter ไปแล้ว (เช่น combobox เลือกพื้นที่) ไม่ต้องยุ่ง
      if (e.defaultPrevented) return;

      const t = e.target;
      if (!t || !t.tagName) return;
      if (t.tagName === 'TEXTAREA') return;                       // Enter = ขึ้นบรรทัดใหม่
      if (t.tagName === 'BUTTON' || t.type === 'submit') return;   // เจตนากดปุ่มนั้นจริง
      if (t.dataset && t.dataset.allowEnter !== undefined) return; // เปิดข้อยกเว้นเฉพาะจุดได้

      e.preventDefault();
    });

    /* ---------- ชั้นที่ 2: กล่องยืนยัน ---------- */
    // จำปุ่มที่ถูกกด เผื่อฟอร์มมีปุ่ม submit หลายตัวที่มี name ต่างกัน
    form.addEventListener('click', (e) => {
      const btn = e.target.closest('button[type="submit"], input[type="submit"]');
      if (btn && form.contains(btn)) lastTrigger = btn;
    });

    form.addEventListener('submit', (e) => {
      if (form.dataset.confirmed === '1') return;   // ผ่านการยืนยันแล้ว ปล่อยไป
      e.preventDefault();
      if (!hasModal) {
        // ไม่มีกล่องยืนยันให้ใช้ -- ยอมถอยไปใช้ confirm() ของเบราว์เซอร์
        // ดีกว่าปล่อยให้บันทึกไปเงียบๆ โดยไม่ถามอะไรเลย
        if (window.confirm(form.dataset.confirmMessage || 'ยืนยันการบันทึกข้อมูลหรือไม่?')) {
          form.dataset.confirmed = '1';
          form.submit();
        }
        return;
      }
      openModal(form);
    });
  });

  if (!hasModal) return;

  btnYes.addEventListener('click', () => {
    if (!pendingForm) return;
    const form = pendingForm;

    // รักษา name/value ของปุ่ม submit ที่ถูกกด -- form.submit() ไม่ส่งค่านี้ให้เอง
    if (lastTrigger && lastTrigger.name && !form.querySelector(`input[type="hidden"][data-confirm-trigger]`)) {
      const keep = document.createElement('input');
      keep.type = 'hidden';
      keep.name = lastTrigger.name;
      keep.value = lastTrigger.value || '';
      keep.setAttribute('data-confirm-trigger', '');
      form.appendChild(keep);
    }

    form.dataset.confirmed = '1';
    closeModal();
    form.submit();
  });

  btnNo.addEventListener('click', closeModal);
  backdrop.addEventListener('click', closeModal);

  document.addEventListener('keydown', (e) => {
    if (!isOpen()) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeModal();
    }
  });
})();
