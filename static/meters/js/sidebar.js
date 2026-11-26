// ปุ่มย่อ/ขยายแถบเมนูบนจอคอม (id=sidebarCollapse ใน base.html)
// สถานะเก็บใน localStorage ของเบราว์เซอร์ -- base.html อ่านค่าตั้งแต่ใน <head> เพื่อไม่ให้แถบกระพริบ
// ตอนย่อ ชื่อเมนูซ่อนด้วย CSS แต่ยังอยู่ใน DOM จึงใส่ title ให้ลิงก์ไว้โชว์เมื่อเอาเมาส์ชี้
(function () {
  var KEY = 'cms.sidebarCollapsed';
  var root = document.documentElement;
  var btn = document.getElementById('sidebarCollapse');
  if (!btn) return;
  var btnLabel = btn.querySelector('[data-sidebar-label]');

  function apply(collapsed) {
    root.classList.toggle('sidebar-collapsed', collapsed);
    var text = collapsed ? 'ขยายเมนู' : 'ย่อเมนู';
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.setAttribute('aria-label', text);
    btn.title = text;
    if (btnLabel) btnLabel.textContent = text;
    document.querySelectorAll('#sidebarPanel nav a').forEach(function (link) {
      var label = link.querySelector('[data-sidebar-label]');
      if (collapsed && label) link.title = label.textContent.trim();
      else link.removeAttribute('title');
    });
  }

  apply(root.classList.contains('sidebar-collapsed'));
  btn.addEventListener('click', function () {
    var collapsed = !root.classList.contains('sidebar-collapsed');
    apply(collapsed);
    try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch (e) { /* โหมดส่วนตัว: ไม่จำสถานะ */ }
  });
})();
