// หน้า meter_form.html -- ปุ่มเปิด/ปิดใช้งานมิเตอร์
// เปิดใช้งาน: ตั้งค่า hidden field แล้ว submit ทันที (ไม่เสี่ยง)
// ปิดใช้งาน: ต้องยืนยันผ่าน modal ก่อน
//
// ค่าใน hidden field ต้องเป็น 'on' / '' ให้ตรงกับที่ view อ่าน
// (request.POST.get('use_or_not') == 'on') -- เดิมใช้ '1'/'0' ซึ่งไม่ตรง ทำให้บันทึกแล้วปิดใช้งานเสมอ
(function () {
  const form = document.getElementById('meterForm');
  const hiddenField = document.getElementById('useOrNotField');
  if (!form || !hiddenField) return;

  const enableBtn = document.getElementById('enableBtn');
  if (enableBtn) {
    enableBtn.addEventListener('click', function () {
      hiddenField.value = 'on';
      form.submit();
    });
  }

  // หน้าเพิ่มมิเตอร์ใหม่: โชว์/ซ่อนช่อง "ระบบไฟฟ้า" ตามประเภทที่เลือก
  // (ไฟ = 8 เท่านั้นที่ใช้ระบบไฟฟ้า) ในหน้าแก้ไขไม่มี select นี้ เพราะประเภทล็อกไว้แล้ว
  const typeSelect = document.getElementById('meterTypeSelect');
  const phaseField = document.getElementById('phaseField');
  if (typeSelect && phaseField) {
    const syncPhaseField = () => {
      phaseField.classList.toggle('hidden', typeSelect.value !== '8');
    };
    typeSelect.addEventListener('change', syncPhaseField);
    syncPhaseField();
  }

  const openBtn = document.getElementById('openDisableBtn');
  if (!openBtn) return;

  const modal = document.getElementById('confirmModal');
  const backdrop = document.getElementById('confirmBackdrop');
  const box = document.getElementById('confirmBox');
  const btnNo = document.getElementById('confirmNo');
  const btnYes = document.getElementById('confirmYes');

  function openModal() {
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
    hiddenField.value = '';
    closeModal();
    form.submit();
  });
})();
