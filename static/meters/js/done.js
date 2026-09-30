// หน้า done.html (Step 4) -- ปุ่มดาวน์โหลดผลนำเข้าเป็นไฟล์ CSV จากตารางบนหน้าจอ
(function () {
  const btn = document.getElementById('btnDownloadCsv');
  if (!btn) return;

  btn.addEventListener('click', () => {
    const rows = [['ลำดับ', 'รหัสสัญญา', 'SubArea', 'ประเภท', 'เลขมิเตอร์', 'สถานะ']];
    document.querySelectorAll('#resultTable tbody tr').forEach((tr) => {
      const cells = Array.from(tr.querySelectorAll('td')).map((td) => td.innerText.trim());
      rows.push(cells);
    });

    const csv = rows
      .map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(','))
      .join('\n');

    // นำ BOM (\ufeff) ไว้หน้าไฟล์ ให้ Excel เปิดไฟล์ CSV ภาษาไทยได้ไม่เป็นตัวยึกยือ
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'utility_import_report.csv';
    a.click();
    URL.revokeObjectURL(url);
  });
})();
