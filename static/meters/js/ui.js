// static/meters/js/ui.js -- ลูกเล่น/ตัวช่วยหน้าจอที่ใช้ร่วมกันทุกหน้า (โหลดจาก base.html)
//
// ทุกอย่างเป็น progressive enhancement: ข้อมูลจริงอยู่ใน HTML ตั้งแต่แรก ถ้า JS ไม่ทำงาน
// หน้ายังใช้งานได้ครบ แค่ไม่มีลูกเล่น -- เปิดใช้ด้วย data-attribute บน element:
//
//   data-count-up            ตัวเลขนับขึ้นจาก 0 ตอนเปิดหน้า (การ์ดสถิติ)
//   data-copy="ข้อความ"       ปุ่มคัดลอกลงคลิปบอร์ด + แจ้งเตือนมุมจอ
//   data-relative-time       <time datetime="ISO"> แสดงเป็น "5 นาทีที่แล้ว" (เวลาเต็มอยู่ใน title)
//                            ถ้ามี [data-relative-full] เป็นพี่น้องถัดไปจะถูกแสดงออกมา
//   data-thai-date-for="id"  ป้ายวันที่ พ.ศ. ใต้ <input type="date"> (เบราว์เซอร์แสดงตามภาษาเครื่อง)
//   data-date-range="N|month" ปุ่มช่วงลัด -- ตั้ง date_from/date_to ในฟอร์มเดียวกันแล้วส่ง
//
// และทำให้ทุกหน้าอัตโนมัติ:
//   - กด "/" เพื่อไปที่ช่องค้นหาแรกของหน้า (ยกเว้นขณะพิมพ์อยู่ในช่องอื่น)
//   - แถบโหลดบางๆ ด้านบนจอเมื่อเปลี่ยนหน้า/ส่งฟอร์ม
//   - ฟอร์ม GET กันกดส่งซ้ำ (ปุ่มขึ้น "กำลังค้นหา...")
//
// เคารพ prefers-reduced-motion -- ผู้ใช้ที่ปิดภาพเคลื่อนไหวจะเห็นค่าสุดท้ายทันที
(function () {
  'use strict';

  var THAI_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'];
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---------------------------------------------------------------- toast
  var toastBox = null;
  function toast(message, tone) {
    if (!toastBox) {
      toastBox = document.createElement('div');
      toastBox.className = 'pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col items-end gap-2';
      toastBox.setAttribute('role', 'status');
      toastBox.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastBox);
    }
    var item = document.createElement('div');
    item.className = 'pointer-events-auto rounded-lg px-4 py-2.5 text-sm font-medium text-white shadow-lg ' +
      'transition duration-300 translate-y-2 opacity-0 ' +
      (tone === 'error' ? 'bg-red-600' : 'bg-gray-900');
    item.textContent = message;
    toastBox.appendChild(item);
    requestAnimationFrame(function () { item.classList.remove('translate-y-2', 'opacity-0'); });
    setTimeout(function () {
      item.classList.add('opacity-0');
      setTimeout(function () { item.remove(); }, 300);
    }, 2200);
  }
  window.cmsToast = toast;

  // ---------------------------------------------------------------- count-up
  function countUp(el) {
    var target = parseInt((el.textContent || '').replace(/[^\d-]/g, ''), 10);
    if (isNaN(target) || target <= 0 || reduceMotion) return;
    var start = null;
    var duration = Math.min(900, 300 + target * 15);
    el.textContent = '0';
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased).toLocaleString('th-TH');
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------- copy
  function copyText(text) {
    // Clipboard API ใช้ได้เฉพาะ https/localhost และเบราว์เซอร์อาจปฏิเสธสิทธิ์ -- ล้มเมื่อไหร่
    // สำรองด้วย textarea + execCommand (ใช้ได้กับ http ภายในองค์กร)
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () { return legacyCopy(text); });
    }
    return legacyCopy(text);
  }

  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); } catch (e) { reject(e); }
      ta.remove();
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;
    e.preventDefault();
    var text = btn.getAttribute('data-copy');
    copyText(text).then(
      function () { toast('คัดลอก "' + text + '" แล้ว'); },
      function () { toast('คัดลอกไม่สำเร็จ', 'error'); }
    );
  });

  // ---------------------------------------------------------------- relative time
  function relativeLabel(date) {
    var diff = Math.round((Date.now() - date.getTime()) / 1000);
    if (diff < 0) return null;
    if (diff < 45) return 'เมื่อสักครู่';
    var min = Math.round(diff / 60);
    if (min < 60) return min + ' นาทีที่แล้ว';
    var hr = Math.round(min / 60);
    if (hr < 24) return hr + ' ชั่วโมงที่แล้ว';
    var day = Math.round(hr / 24);
    if (day === 1) return 'เมื่อวาน';
    if (day < 7) return day + ' วันที่แล้ว';
    return null;   // เก่ากว่า 1 สัปดาห์ -- แสดงวันที่เต็มตามเดิมอ่านง่ายกว่า
  }

  function refreshRelativeTimes() {
    document.querySelectorAll('time[data-relative-time]').forEach(function (el) {
      var date = new Date(el.getAttribute('datetime'));
      if (isNaN(date.getTime())) return;
      var label = relativeLabel(date);
      if (!label) return;
      el.textContent = label;
      var full = el.parentElement && el.parentElement.querySelector('[data-relative-full]');
      if (full) full.classList.remove('hidden');
    });
  }

  // ---------------------------------------------------------------- Thai date labels
  function thaiDateLabel(value) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!m) return '';
    return parseInt(m[3], 10) + ' ' + THAI_MONTHS[parseInt(m[2], 10) - 1] + ' ' + (parseInt(m[1], 10) + 543);
  }

  function bindThaiDateLabels() {
    document.querySelectorAll('[data-thai-date-for]').forEach(function (label) {
      var input = document.getElementById(label.getAttribute('data-thai-date-for'));
      if (!input) return;
      var sync = function () { label.textContent = thaiDateLabel(input.value); };
      input.addEventListener('change', sync);
      input.addEventListener('input', sync);
      sync();
    });
  }

  function isoDate(d) {
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + mm + '-' + dd;
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-date-range]');
    if (!btn) return;
    var form = btn.closest('form');
    if (!form) return;
    var from = form.querySelector('[name="date_from"]');
    var to = form.querySelector('[name="date_to"]');
    if (!from || !to) return;
    var today = new Date();
    var start = new Date(today);
    var range = btn.getAttribute('data-date-range');
    if (range === 'month') {
      start = new Date(today.getFullYear(), today.getMonth(), 1);
    } else {
      start.setDate(today.getDate() - (parseInt(range, 10) || 0));
    }
    from.value = isoDate(start);
    to.value = isoDate(today);
    from.dispatchEvent(new Event('change'));
    to.dispatchEvent(new Event('change'));
    if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
  });

  // ---------------------------------------------------------------- "/" = focus search
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    var active = document.activeElement;
    if (active && (/^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName) || active.isContentEditable)) return;
    var search = document.querySelector('main input[type="search"]');
    if (!search) return;
    e.preventDefault();
    search.focus();
    search.select();
  });

  // ---------------------------------------------------------------- top progress bar
  var bar = null;
  function startProgress() {
    if (reduceMotion) return;
    if (!bar) {
      bar = document.createElement('div');
      bar.setAttribute('aria-hidden', 'true');
      bar.className = 'fixed left-0 top-0 z-[70] h-0.5 bg-brand-500 transition-all duration-[1500ms] ease-out';
      bar.style.width = '0';
      document.body.appendChild(bar);
    }
    bar.style.opacity = '1';
    bar.style.width = '0';
    requestAnimationFrame(function () { requestAnimationFrame(function () { bar.style.width = '85%'; }); });
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (a.target === '_blank' || a.hasAttribute('download')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(mailto|tel|javascript):/i.test(href)) return;
    if (/\/export\/|\/excel\//.test(a.pathname)) return;   // ไฟล์ดาวน์โหลด -- หน้าไม่เปลี่ยน
    startProgress();
  });

  document.addEventListener('submit', function (e) {
    if (e.defaultPrevented) return;
    var form = e.target;
    var method = (form.getAttribute('method') || 'get').toLowerCase();
    if (method !== 'get') return;   // ฟอร์ม POST มีตัวจัดการของตัวเอง (confirm_submit.js)
    startProgress();
    var btn = form.querySelector('button[type="submit"]');
    if (btn && !btn.disabled) {
      btn.setAttribute('aria-busy', 'true');
      btn.dataset.originalText = btn.textContent;
      btn.textContent = 'กำลังค้นหา...';
      btn.disabled = true;
    }
  });

  // กลับมาหน้าเดิมด้วยปุ่ม back -- เบราว์เซอร์คืนหน้าจาก cache พร้อมสถานะปุ่มที่ disabled ค้างไว้
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    if (bar) { bar.style.opacity = '0'; }
    document.querySelectorAll('button[aria-busy="true"]').forEach(function (btn) {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      if (btn.dataset.originalText) btn.textContent = btn.dataset.originalText;
    });
  });

  // ---------------------------------------------------------------- init
  function init() {
    document.querySelectorAll('[data-count-up]').forEach(countUp);
    refreshRelativeTimes();
    setInterval(refreshRelativeTimes, 60000);
    bindThaiDateLabels();
    var search = document.querySelector('main input[type="search"]');
    if (search && !search.title) search.title = 'กด / เพื่อค้นหา';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
