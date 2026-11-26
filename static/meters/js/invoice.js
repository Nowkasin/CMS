// static/meters/js/invoice.js -- หน้าใบแจ้งหนี้ (invoice_search.html / invoice_print.html)
//   - เลือกทั้งหมด / นับจำนวนใบที่เลือก (ใบเดียวกันอาจมีหลายแถว นับตามค่า doc ที่ไม่ซ้ำ)
//   - ปุ่มพิมพ์กดได้เมื่อเลือกอย่างน้อย 1 ใบ
//   - ป้ายเดือน พ.ศ. ใต้ช่องประจำงวด (202611 -> พฤศจิกายน 2569)
//   - หน้าพิมพ์: ปุ่ม [data-print] สั่ง window.print()
(function () {
  'use strict';

  var THAI_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'];

  var checks = Array.prototype.slice.call(document.querySelectorAll('[data-invoice-check]'));
  var selectAll = document.getElementById('invoiceSelectAll');
  var printBtn = document.getElementById('invoicePrintBtn');
  var counter = document.getElementById('invoiceSelectedCount');

  function sync() {
    var docs = {};
    checks.forEach(function (c) { if (c.checked) docs[c.value] = true; });
    var count = Object.keys(docs).length;
    if (counter) counter.textContent = count;
    if (printBtn) printBtn.disabled = count === 0;
    if (selectAll) {
      var checked = checks.filter(function (c) { return c.checked; }).length;
      selectAll.checked = checked > 0 && checked === checks.length;
      selectAll.indeterminate = checked > 0 && checked < checks.length;
    }
  }

  checks.forEach(function (c) {
    c.addEventListener('change', function () {
      // ติ๊กแถวหนึ่ง = ติ๊กทุกแถวของใบแจ้งหนี้เดียวกัน ให้เห็นชัดว่าจะพิมพ์รวมกัน
      checks.forEach(function (other) { if (other.value === c.value) other.checked = c.checked; });
      sync();
    });
  });
  if (selectAll) {
    selectAll.addEventListener('change', function () {
      checks.forEach(function (c) { c.checked = selectAll.checked; });
      sync();
    });
  }
  if (checks.length) sync();

  var period = document.querySelector('[data-period-for]');
  if (period) {
    var label = document.getElementById(period.getAttribute('data-period-for'));
    var syncPeriod = function () {
      var m = /^(\d{4})(\d{2})$/.exec(period.value.trim());
      var month = m ? parseInt(m[2], 10) : 0;
      label.textContent = (m && month >= 1 && month <= 12)
        ? THAI_MONTHS[month - 1] + ' ' + (parseInt(m[1], 10) + 543) : '';
    };
    period.addEventListener('input', syncPeriod);
    syncPeriod();
  }

  document.querySelectorAll('[data-print]').forEach(function (btn) {
    btn.addEventListener('click', function () { window.print(); });
  });
})();
