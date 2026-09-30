// หน้า edit_meter.html -- checkbox เปิด/ปิดการ์ดมิเตอร์น้ำ-ไฟ
// ปิดอยู่ = ทำให้ช่องในการ์ดนั้น disabled (ช่องที่ disabled จะไม่ถูกส่งไปกับฟอร์ม)
(function () {
  function wireToggle(checkboxId, fieldsId) {
    const checkbox = document.getElementById(checkboxId);
    const fields = document.getElementById(fieldsId);
    if (!checkbox || !fields) return;

    const inputs = fields.querySelectorAll('input, select');

    function sync() {
      const on = checkbox.checked;
      fields.classList.toggle('opacity-40', !on);
      fields.classList.toggle('pointer-events-none', !on);
      inputs.forEach((el) => (el.disabled = !on));
    }

    checkbox.addEventListener('change', sync);
  }

  wireToggle('waterEnable', 'waterFields');
  wireToggle('electricEnable', 'electricFields');
})();
