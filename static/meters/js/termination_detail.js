// หน้า termination_detail.html -- modal ยืนยันก่อนบันทึกการยกเลิกสัญญา
(function () {
  const openBtn = document.getElementById('openConfirmBtn');
  const modal = document.getElementById('confirmModal');
  const backdrop = document.getElementById('confirmBackdrop');
  const box = document.getElementById('confirmBox');
  const btnNo = document.getElementById('confirmNo');
  const btnYes = document.getElementById('confirmYes');
  const form = document.getElementById('terminationForm');

  if (!openBtn || !modal || !form) return;

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
    closeModal();
    form.submit();
  });
})();
