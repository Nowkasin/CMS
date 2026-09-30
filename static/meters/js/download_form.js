// หน้า download_form.html -- ติ๊กเลือกแถวก่อนดาวน์โหลด Excel
// คลิกที่ไหนในแถวก็ติ๊กได้ + checkbox "เลือกทั้งหมด" ที่มีสถานะ indeterminate
(function () {
  const body = document.getElementById('rowsBody');
  const selectAll = document.getElementById('selectAllRows');
  if (!body) return;

  function syncRowHighlight(row) {
    const checkbox = row.querySelector('.row-check');
    row.classList.toggle('row-selected', checkbox.checked);
  }

  function syncSelectAllState() {
    if (!selectAll) return;
    const checks = body.querySelectorAll('.row-check');
    const checkedCount = body.querySelectorAll('.row-check:checked').length;
    selectAll.checked = checks.length > 0 && checkedCount === checks.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < checks.length;
  }

  // คลิกที่ไหนในแถวก็ toggle checkbox ได้ (ยกเว้นคลิกที่ checkbox เอง กันติ๊กซ้อนสองรอบ)
  body.querySelectorAll('tr.row-clickable').forEach(function (row) {
    const checkbox = row.querySelector('.row-check');
    syncRowHighlight(row);

    row.addEventListener('click', function (e) {
      if (e.target === checkbox) return;
      checkbox.checked = !checkbox.checked;
      syncRowHighlight(row);
      syncSelectAllState();
    });

    checkbox.addEventListener('change', function () {
      syncRowHighlight(row);
      syncSelectAllState();
    });
  });

  if (selectAll) {
    selectAll.addEventListener('change', function () {
      body.querySelectorAll('.row-check').forEach(function (c) {
        c.checked = selectAll.checked;
        syncRowHighlight(c.closest('tr'));
      });
    });
  }

  syncSelectAllState();
})();
