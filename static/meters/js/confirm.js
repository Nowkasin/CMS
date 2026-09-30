// หน้า confirm.html (Step 3) -- เปิด/ปิดปุ่ม "ยืนยันนำเข้าข้อมูล" ตาม checkbox ยืนยัน
(function () {
  const checkbox = document.getElementById('confirmCheckbox');
  const btn = document.getElementById('btnConfirm');
  if (!checkbox || !btn) return;

  checkbox.addEventListener('change', () => {
    if (checkbox.checked) {
      btn.disabled = false;
      btn.classList.remove('bg-gray-200', 'text-gray-400');
      btn.classList.add('bg-brand-500', 'hover:bg-brand-600', 'text-white');
    } else {
      btn.disabled = true;
      btn.classList.add('bg-gray-200', 'text-gray-400');
      btn.classList.remove('bg-brand-500', 'hover:bg-brand-600', 'text-white');
    }
  });
})();
