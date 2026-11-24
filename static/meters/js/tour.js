// static/meters/js/tour.js -- ทัวร์พาคลิกทีละขั้นในแต่ละหน้า (โหลดจาก base.html)
//
// วิธีทำงาน
//   - หน้าไหนมีทัวร์ ดูจาก <body data-page="url_name"> เทียบกับ TOURS ข้างล่าง
//   - แต่ละขั้นชี้ element ด้วย CSS selector (ส่วนใหญ่เป็น [data-tour="..."] ที่ติดไว้ใน template)
//     ใส่ได้หลายตัวเลือก ใช้ตัวแรกที่มองเห็นอยู่ -- เช่นตารางบนจอใหญ่ / การ์ดบนมือถือ
//     ขั้นที่หา element ไม่เจอหรือถูกซ่อนจะถูกข้ามเอง (ไม่ทำให้ทัวร์พัง)
//   - เปิดทัวร์: ปุ่ม "พาชมหน้านี้" บนแถบบน, ลิงก์ในหน้าคู่มือ (?tour=1) หรือการ์ดชวนที่โผล่
//     ครั้งแรกที่เข้าหน้านั้น (จำใน localStorage ต่อเบราว์เซอร์ -- ถ้าเก็บไม่ได้ก็แค่ชวนซ้ำ)
//   - คีย์ลัด: → / Enter ถัดไป, ← ย้อนกลับ, Esc ปิด
//
// เพิ่มทัวร์หน้าใหม่: ติด data-tour="ชื่อ" ที่ element ใน template แล้วเพิ่ม TOURS['url_name']
// รักษาชื่อ data-tour เดิมไว้ ถ้าเปลี่ยนต้องแก้ที่นี่พร้อมกัน (ดู AGENTS.md)
(function () {
  'use strict';

  var TOURS = {
    help: [
      { target: ['[data-tour="sidebar"]'], title: 'เมนูหลัก',
        body: 'เมนูทางซ้ายแสดงเฉพาะงานที่บัญชีของคุณได้รับสิทธิ์ บนมือถือกดปุ่มขีด 3 ขีดมุมซ้ายบนเพื่อเปิดเมนู' },
      { target: ['[data-tour="tour-button"]'], title: 'ปุ่ม "พาชมหน้านี้"',
        body: 'เปิดหน้าไหนแล้วไม่แน่ใจ กดปุ่มนี้ ระบบจะพาชี้ทีละจุดของหน้านั้นเหมือนตอนนี้' },
      { target: ['[data-tour="help-link"]'], title: 'กลับมาที่คู่มือได้ทุกเมื่อ',
        body: 'ไอคอนเครื่องหมายคำถามพากลับมาหน้าคู่มือนี้ ซึ่งมีภาพเคลื่อนไหวสาธิตทุกขั้นตอน' },
      { target: ['[data-tour="help-sections"]'], title: 'เลือกหัวข้อที่ต้องการ',
        body: 'แต่ละหัวข้อมีขั้นตอนเป็นข้อๆ และปุ่ม "ลองทำในหน้าจริง" ที่พาไปหน้านั้นพร้อมเปิดทัวร์ให้' },
    ],

    dashboard: [
      { target: ['[data-tour="stats"]'], title: 'ภาพรวมมิเตอร์',
        body: 'จำนวนมิเตอร์น้ำ ไฟฟ้า และสัญญาที่ผูกอยู่ การ์ด "รอ Gen เลข" เป็นสีส้มเมื่อมีมิเตอร์ที่ยังไม่มีเลข' },
      { target: ['[data-tour="type-tabs"]'], title: 'กรองตามประเภท',
        body: 'สลับดูเฉพาะพื้นที่ที่มีมิเตอร์น้ำหรือมิเตอร์ไฟฟ้า ตัวเลขในวงเล็บคือจำนวนพื้นที่ในตาราง' },
      { target: ['[data-tour="search"]'], title: 'ค้นหา',
        body: 'พิมพ์รหัสสัญญา ชื่อลูกหนี้ หรือเลขมิเตอร์ แล้วกดค้นหา (กดปุ่ม / บนคีย์บอร์ดเพื่อมาที่ช่องนี้ได้ทันที)' },
      { target: ['[data-tour="table"]', '[data-tour="table-mobile"]'], title: 'รายการพื้นที่',
        body: 'หนึ่งแถวคือหนึ่งพื้นที่ย่อย กดไอคอนดินสอเพื่อแก้เลขมิเตอร์และบันทึกเลขอ่านรายเดือนของพื้นที่นั้น' },
      { target: ['[data-tour="export"]'], title: 'ส่งออก Excel',
        body: 'ได้ไฟล์ Excel ตามตัวกรองและคำค้นที่เห็นบนจอตอนนี้' },
    ],

    edit_meter: [
      { target: ['form[method="get"]'], title: 'เลือกรอบบิลก่อน',
        body: 'เลือกเดือนและปี พ.ศ. ของรอบบิลที่จะบันทึก ระบบจะโหลดเลขอ่านของรอบนั้นขึ้นมาให้' },
      { target: ['#waterEnable'], title: 'มิเตอร์น้ำ',
        body: 'ติ๊กเพื่อแก้ไขมิเตอร์น้ำ กรอกเลขเครื่องวัด และเลขอ่านก่อน-หลังของรอบนี้ (ถ้าเว้นเลขเครื่องวัดว่าง เลขเดิมจะถูกลบ)' },
      { target: ['#electricEnable'], title: 'มิเตอร์ไฟฟ้า',
        body: 'เหมือนน้ำ และเลือกระบบไฟฟ้า 1 เฟส / 3 เฟส ได้ด้วย' },
      { target: ['form[data-confirm-submit] button[type="submit"]'], title: 'บันทึก',
        body: 'ระบบจะสรุปค่าที่กรอกให้ตรวจอีกครั้งก่อนบันทึกจริง เลขอ่านหลังต้องไม่น้อยกว่าเลขอ่านก่อน' },
    ],

    meter_list: [
      { target: ['[data-tour="add"]'], title: 'เพิ่มมิเตอร์ใหม่',
        body: 'ลงทะเบียนมิเตอร์ให้พื้นที่ย่อย ถ้าเป็นมิเตอร์น้ำและยังไม่มีเลข ระบบจะ Gen เลข (W001...) ให้' },
      { target: ['[data-tour="filters"]'], title: 'กรองและค้นหา',
        body: 'ดูเฉพาะมิเตอร์ที่ใช้งาน/ปิดใช้งาน เลือกประเภท หรือค้นจากสถานที่ เลขมิเตอร์ รหัสสัญญา' },
      { target: ['[data-tour="table"]'], title: 'รายการมิเตอร์',
        body: 'เลขมิเตอร์อยู่ซ้ายสุด ชี้เมาส์ที่แถวจะมีปุ่มคัดลอกเลข กดดินสอทางขวาเพื่อแก้ไขหรือปิดใช้งาน' },
    ],

    meter_new: [
      { target: ['#subareaCombo', '#subareaSelect'], title: 'เลือกพื้นที่ย่อย',
        body: 'พิมพ์ค้นหาชื่อหรือรหัสพื้นที่ แล้วเลือกจากรายการ สถานที่และพื้นที่จะถูกเติมให้อัตโนมัติ' },
      { target: ['#meterTypeSelect'], title: 'ประเภทมิเตอร์',
        body: 'เลือกน้ำหรือไฟฟ้า (แก้ภายหลังไม่ได้)' },
      { target: ['#meterNoInput'], title: 'เลขประจำเครื่องวัด',
        body: 'มิเตอร์น้ำเว้นว่างได้ ระบบจะ Gen เลขให้ มิเตอร์ไฟฟ้าใส่เลขจริงจากการไฟฟ้า' },
      { target: ['#meterForm button[type="submit"]'], title: 'บันทึก',
        body: 'ระบบจะสรุปค่าที่กรอกให้ตรวจก่อนบันทึก' },
    ],

    meter_edit: [
      { target: ['#meterNoInput'], title: 'แก้เลขมิเตอร์',
        body: 'ถ้าจะเปลี่ยนเลขให้พิมพ์เลขใหม่ ห้ามเว้นว่าง เพราะเลขเดิมจะหายถาวร' },
      { target: ['#openDisableBtn', '#enableBtn'], title: 'เปิด/ปิดใช้งาน',
        body: 'เลิกใช้มิเตอร์ตัวนี้ให้กดปิดใช้งาน ข้อมูลยังอยู่และเปิดกลับได้' },
      { target: ['#meterForm button[type="submit"]'], title: 'บันทึก',
        body: 'ระบบจะสรุปค่าที่เปลี่ยนให้ตรวจก่อนบันทึก' },
    ],

    step1: [
      { target: ['#billing-month'], title: '1. เลือกรอบบิล',
        body: 'เลือกเดือนและปี พ.ศ. ของค่าน้ำ-ค่าไฟที่จะนำเข้า ค่าเริ่มต้นคือเดือนที่แล้ว' },
      { target: ['#dropzone'], title: '2. เลือกไฟล์ Excel',
        body: 'ลากไฟล์ .xlsx มาวาง หรือกดเพื่อเลือกไฟล์ ต้องมีชีทชื่อขึ้นต้นด้วย "สัญญาปี" และคำว่า น้ำ / ไฟ' },
      { target: ['#btnSubmit'], title: '3. ไปตรวจสอบข้อมูล',
        body: 'ขั้นนี้ยังไม่บันทึกอะไรลงระบบ ระบบจะอ่านไฟล์แล้วพาไปหน้าตรวจสอบ' },
    ],

    step2: [
      { target: ['[data-tour="status-tabs"]'], title: 'ดูทีละสถานะ',
        body: 'ถ้ามีแถวที่ผิดพลาด หน้าจะเปิดแท็บ "มีปัญหา" ให้ก่อน แต่ละแถวบอกเลขแถวใน Excel ที่ต้องกลับไปแก้' },
      { target: ['[data-tour="table"]'], title: 'ตรวจรายละเอียด',
        body: '"มีในระบบแล้ว" = จะอัปเดตมิเตอร์ตัวเดิม ไม่สร้างซ้ำ  "ข้าม" = พื้นที่ที่ไม่คิดค่า' },
      { target: ['[data-tour="next"]'], title: 'ถัดไป',
        body: 'ไปต่อได้เมื่อไม่มีแถวที่มีปัญหา ถ้ามี ให้แก้ในไฟล์ Excel แล้วอัปโหลดใหม่' },
    ],

    step3: [
      { target: ['#confirmCheckbox'], title: 'ยืนยันว่าตรวจแล้ว',
        body: 'ติ๊กยืนยันก่อน ปุ่มบันทึกจึงจะกดได้' },
      { target: ['#btnConfirm'], title: 'บันทึกลงระบบ',
        body: 'บันทึกทั้งไฟล์ในครั้งเดียว ถ้าแถวใดล้ม ระบบจะไม่บันทึกอะไรเลยและบอกว่าแถวไหนมีปัญหา' },
    ],

    step4: [
      { target: ['[data-tour="csv"]'], title: 'เก็บผลไว้อ้างอิง',
        body: 'ดาวน์โหลดผลการนำเข้าเป็นไฟล์ CSV ได้ ประวัติการนำเข้าทุกครั้งดูย้อนหลังได้ที่เมนูประวัติการใช้งาน' },
    ],

    download_form: [
      { target: ['[data-tour="period"]'], title: 'เลือกเดือน-ปี แล้วค้นหา',
        body: 'ระบบจะแสดงรายการสัญญาและเลขอ่านมิเตอร์ของรอบบิลนั้น' },
      { target: ['#selectAllRows'], title: 'เลือกรายการ',
        body: 'ติ๊กทีละแถว หรือเลือกทั้งหมดในคลิกเดียว' },
      { target: ['[data-tour="download"]'], title: 'ดาวน์โหลด',
        body: 'ได้ไฟล์ Excel แยกชีทน้ำประปาและไฟฟ้า เฉพาะแถวที่เลือก' },
    ],

    phase_list: [
      { target: ['[data-tour="add"]'], title: 'เพิ่มระบบไฟฟ้า',
        body: 'ตัวเลือกนี้จะไปโผล่ใน dropdown "ระบบไฟฟ้า" ของหน้ามิเตอร์' },
      { target: ['[data-tour="status-tabs"]'], title: 'ใช้งาน / ปิดใช้งาน',
        body: 'ปิดใช้งานแทนการลบ มิเตอร์ที่ใช้ค่านั้นอยู่จะไม่ได้รับผลกระทบ' },
    ],

    termination_search: [
      { target: ['[data-tour="tabs"]'], title: 'คิวงาน',
        body: 'แท็บ "หมดอายุแล้ว รอบันทึกยกเลิก" คืองานที่ต้องทำ เรียงจากสัญญาที่หมดอายุนานที่สุด' },
      { target: ['[data-tour="filters"]'], title: 'กรองและค้นหา',
        body: 'ค่าเริ่มต้นแสดงเฉพาะสัญญาจริง สลับดูฉบับร่างได้จากช่องซ้ายสุด' },
      { target: ['[data-tour="table"]', '[data-tour="table-mobile"]'], title: 'เลือกสัญญา',
        body: 'กด "บันทึกยกเลิก" ที่แถวของสัญญาเพื่อเข้าไปกรอกข้อมูลการยกเลิก' },
    ],

    termination_detail: [
      { target: ['#terminationCase'], title: 'เลือกกรณีการยกเลิก',
        body: 'ยกเลิกก่อนครบอายุ = จัดการต่อได้ 2 เดือน (ต้องระบุวันที่แจ้งยกเลิก)  สิ้นสุดและไม่ต่อ = 1 เดือน' },
      { target: ['#openConfirmBtn'], title: 'บันทึก',
        body: 'ระบบจะสรุปงวดสุดท้ายที่จัดการได้ให้ดูก่อนยืนยัน บันทึกแล้วแก้ไม่ได้ ถ้าผิดให้ลบแล้วบันทึกใหม่' },
      { target: ['#openDeleteBtn'], title: 'ลบรายการยกเลิก',
        body: 'ใช้เมื่อบันทึกผิด ระบบจะคืนสถานะสัญญาเดิมให้' },
    ],

    invoice_search: [
      { target: ['[data-tour="filters"]'], title: 'ค้นหารายการตั้งหนี้',
        body: 'เลือกปีที่สร้างสัญญา (บังคับ) และใส่ประจำงวดแบบปี ค.ศ.+เดือน เช่น 202611 ใต้ช่องจะแสดงเดือน พ.ศ. ให้ตรวจ' },
      { target: ['[data-tour="table"]'], title: 'เลือกใบแจ้งหนี้',
        body: 'ติ๊กรายการที่ต้องการพิมพ์ แถวที่มีเลขตั้งหนี้ SAP เดียวกันอยู่ในใบเดียวกันและถูกติ๊กพร้อมกัน' },
      { target: ['[data-tour="print"]'], title: 'พิมพ์ใบแจ้งหนี้',
        body: 'เปิดหน้าใบแจ้งหนี้ขนาด A4 หน้าละหนึ่งใบ แล้วสั่งพิมพ์หรือบันทึกเป็น PDF จากหน้านั้น' },
    ],

    activity_log: [
      { target: ['[data-tour="tabs"]'], title: 'เลือกประเภทเหตุการณ์',
        body: 'ดูเฉพาะการนำเข้าไฟล์ การแก้มิเตอร์ การยกเลิกสัญญา ฯลฯ' },
      { target: ['[data-tour="filters"]'], title: 'กรองผู้ทำรายการและช่วงวันที่',
        body: 'ใช้ปุ่มช่วงลัด วันนี้ / 7 วัน / 30 วัน / เดือนนี้ ได้ วันที่แสดงเป็น พ.ศ. ใต้ช่อง' },
      { target: ['[data-tour="table"]', '[data-tour="table-mobile"]'], title: 'รายการเหตุการณ์',
        body: 'ล่าสุดอยู่บนสุด มีรายการใหม่ระหว่างเปิดหน้า ระบบจะขึ้นแถบแจ้งให้โหลดใหม่' },
    ],
  };

  var STORE_PREFIX = 'cms-tour-seen:';
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var page = document.body ? document.body.getAttribute('data-page') : '';

  function storeGet(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function storeSet(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* โหมดส่วนตัว */ } }

  function isVisible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    var style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  }

  function resolve(step) {
    for (var i = 0; i < step.target.length; i++) {
      var list = document.querySelectorAll(step.target[i]);
      for (var j = 0; j < list.length; j++) {
        if (isVisible(list[j])) return list[j];
      }
    }
    return null;
  }

  function stepsForPage() {
    var steps = TOURS[page] || [];
    return steps.filter(function (s) { return resolve(s); });
  }

  // ---------------------------------------------------------------- UI
  var overlay, spot, card, steps = [], index = 0, current = null, lastFocus = null;

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html) n.innerHTML = html;
    return n;
  }

  function build() {
    overlay = el('div', 'fixed inset-0 z-[80]');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.addEventListener('click', end);

    // ช่องส่องไฟ -- เงาขนาดใหญ่รอบกรอบทำให้ส่วนอื่นของจอมืดลง และเลื่อนตามขั้นแบบนุ่มนวล
    // ห้ามใช้ class ring-* ของ Tailwind ที่ตัวนี้ -- ring เขียน box-shadow ทับเงามืดรอบกรอบ
    spot = el('div', 'pointer-events-none fixed z-[81] rounded-xl');
    spot.style.border = '2px solid #006767';
    spot.style.boxShadow = '0 0 0 9999px rgba(15, 23, 42, 0.55)';
    if (!reduceMotion) spot.style.transition = 'top .35s ease, left .35s ease, width .35s ease, height .35s ease';
    var pulse = el('span', 'absolute inset-0 rounded-xl ring-4 ring-brand-500/40');
    if (!reduceMotion) pulse.style.animation = 'cmsTourPulse 1.6s ease-out infinite';
    spot.appendChild(pulse);

    card = el('div', 'fixed z-[82] w-[min(22rem,calc(100vw-2rem))] rounded-2xl bg-white p-5 shadow-2xl ring-1 ring-gray-900/10');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-labelledby', 'cmsTourTitle');
    card.setAttribute('aria-describedby', 'cmsTourBody');
    if (!reduceMotion) card.style.transition = 'top .35s ease, left .35s ease, opacity .2s ease';

    if (!document.getElementById('cmsTourStyle')) {
      var style = el('style');
      style.id = 'cmsTourStyle';
      style.textContent = '@keyframes cmsTourPulse{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(1.08)}}';
      document.head.appendChild(style);
    }
    document.body.appendChild(overlay);
    document.body.appendChild(spot);
    document.body.appendChild(card);
  }

  function render() {
    var step = steps[index];
    var total = steps.length;
    var dots = '';
    for (var i = 0; i < total; i++) {
      dots += '<span class="h-1.5 rounded-full transition-all ' +
        (i === index ? 'w-5 bg-brand-500' : 'w-1.5 bg-gray-200') + '"></span>';
    }
    card.innerHTML =
      '<div class="mb-2 flex items-center justify-between gap-3">' +
        '<span class="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">ขั้นที่ ' + (index + 1) + ' / ' + total + '</span>' +
        '<button type="button" data-tour-close class="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600" aria-label="ปิดทัวร์">' +
          '<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>' +
        '</button>' +
      '</div>' +
      '<h2 id="cmsTourTitle" class="text-base font-bold text-gray-900"></h2>' +
      '<p id="cmsTourBody" class="mt-1 text-sm leading-6 text-gray-600"></p>' +
      '<div class="mt-4 flex items-center justify-between gap-3">' +
        '<div class="flex items-center gap-1" aria-hidden="true">' + dots + '</div>' +
        '<div class="flex gap-2">' +
          (index > 0 ? '<button type="button" data-tour-prev class="rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50">ย้อนกลับ</button>' : '') +
          '<button type="button" data-tour-next class="rounded-lg bg-brand-500 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-600">' +
            (index === total - 1 ? 'เข้าใจแล้ว' : 'ถัดไป') + '</button>' +
        '</div>' +
      '</div>';
    // ข้อความใส่ผ่าน textContent -- กันกรณีมีคนใส่ HTML ลงในข้อความทัวร์ภายหลัง
    card.querySelector('#cmsTourTitle').textContent = step.title;
    card.querySelector('#cmsTourBody').textContent = step.body;
    card.querySelector('[data-tour-close]').addEventListener('click', end);
    card.querySelector('[data-tour-next]').addEventListener('click', next);
    var prevBtn = card.querySelector('[data-tour-prev]');
    if (prevBtn) prevBtn.addEventListener('click', prev);

    current = resolve(step);
    if (!current) { next(); return; }
    current.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
    // รอการเลื่อนจอจบก่อนวางกรอบ (smooth scroll ไม่มี event จบที่ใช้ได้ทุกเบราว์เซอร์)
    setTimeout(place, reduceMotion ? 0 : 350);
    place();
    card.querySelector('[data-tour-next]').focus();
  }

  function place() {
    if (!current || !card) return;
    var pad = 6;
    var r = current.getBoundingClientRect();
    spot.style.top = (r.top - pad) + 'px';
    spot.style.left = (r.left - pad) + 'px';
    spot.style.width = (r.width + pad * 2) + 'px';
    spot.style.height = (r.height + pad * 2) + 'px';

    var vw = window.innerWidth, vh = window.innerHeight;
    var cw = card.offsetWidth, ch = card.offsetHeight, gap = 14;
    var top, left;
    if (r.bottom + gap + ch <= vh) {          // ใต้ element
      top = r.bottom + gap;
    } else if (r.top - gap - ch >= 0) {       // เหนือ element
      top = r.top - gap - ch;
    } else {                                   // element สูงเต็มจอ -- วางมุมล่าง
      top = vh - ch - 16;
    }
    left = Math.min(Math.max(16, r.left), vw - cw - 16);
    card.style.top = Math.max(16, top) + 'px';
    card.style.left = left + 'px';
  }

  function next() {
    if (index < steps.length - 1) { index++; render(); } else { end(); }
  }
  function prev() {
    if (index > 0) { index--; render(); }
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); end(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
  }

  function start() {
    steps = stepsForPage();
    if (!steps.length) return;
    dismissOffer();
    lastFocus = document.activeElement;
    index = 0;
    build();
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    render();
  }

  function end() {
    storeSet(STORE_PREFIX + page, '1');
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('resize', place);
    window.removeEventListener('scroll', place, true);
    [overlay, spot, card].forEach(function (n) { if (n) n.remove(); });
    overlay = spot = card = current = null;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  window.cmsStartTour = start;

  // ---------------------------------------------------------------- การ์ดชวนดูทัวร์ครั้งแรก
  var offer = null;
  function dismissOffer() {
    if (offer) { offer.remove(); offer = null; }
  }

  function showOffer() {
    offer = el('div', 'fixed bottom-4 left-4 z-[60] w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-brand-100 bg-white p-4 shadow-xl transition duration-300 translate-y-3 opacity-0');
    offer.setAttribute('role', 'status');
    offer.innerHTML =
      '<div class="flex items-start gap-3">' +
        '<span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-lg" aria-hidden="true">👋</span>' +
        '<div class="min-w-0">' +
          '<p class="text-sm font-semibold text-gray-900">เข้าหน้านี้ครั้งแรก?</p>' +
          '<p class="mt-0.5 text-xs leading-5 text-gray-500">ให้ระบบพาชมจุดสำคัญของหน้านี้ ใช้เวลาไม่ถึงนาที</p>' +
          '<div class="mt-3 flex gap-2">' +
            '<button type="button" data-offer-start class="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600">เริ่มทัวร์</button>' +
            '<button type="button" data-offer-skip class="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50">ไม่ต้อง</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(offer);
    offer.querySelector('[data-offer-start]').addEventListener('click', start);
    offer.querySelector('[data-offer-skip]').addEventListener('click', function () {
      storeSet(STORE_PREFIX + page, '1');
      dismissOffer();
    });
    requestAnimationFrame(function () {
      if (offer) offer.classList.remove('translate-y-3', 'opacity-0');
    });
  }

  // ---------------------------------------------------------------- init
  function init() {
    if (!TOURS[page] || !stepsForPage().length) return;
    var button = document.getElementById('tourStart');
    if (button) {
      button.hidden = false;
      button.addEventListener('click', start);
    }
    var params = new URLSearchParams(window.location.search);
    if (params.get('tour') === '1') {
      setTimeout(start, 300);
    } else if (!storeGet(STORE_PREFIX + page)) {
      setTimeout(showOffer, 1200);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
