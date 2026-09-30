// หน้า phase_form.html (Master ระบบไฟฟ้า) -- ปุ่มเปิด/ปิดใช้งาน
// เปิดใช้งาน: ตั้งค่า hidden field แล้ว submit ทันที (ไม่เสี่ยง)
// ปิดใช้งาน: ต้องยืนยันผ่าน modal ก่อน
//
// ค่าใน hidden field ต้องเป็น 'on' / '' ให้ตรงกับที่ view อ่าน
// (request.POST.get('use_or_not') == 'on')
(function () {
  const form = document.getElementById('phaseForm');
  const hiddenField = document.getElementById('useOrNotField');
  if (!form || !hiddenField) return;

  const enableBtn = document.getElementById('enableBtn');
  if (enableBtn) {
    enableBtn.addEventListener('click', function () {
      hiddenField.value = 'on';
      form.submit();
    });
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
