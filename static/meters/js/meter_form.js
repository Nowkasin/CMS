// หน้า meter_form.html -- ปุ่มเปิด/ปิดใช้งานมิเตอร์
// เปิดใช้งาน: ตั้งค่า hidden field แล้ว submit ทันที (ไม่เสี่ยง)
// ปิดใช้งาน: ต้องยืนยันผ่าน modal ก่อน
//
// ค่าใน hidden field ต้องเป็น 'on' / '' ให้ตรงกับที่ view อ่าน
// (request.POST.get('use_or_not') == 'on') -- เดิมใช้ '1'/'0' ซึ่งไม่ตรง ทำให้บันทึกแล้วปิดใช้งานเสมอ
(function () {
  const form = document.getElementById('meterForm');
  const hiddenField = document.getElementById('useOrNotField');
  if (!form || !hiddenField) return;

  const enableBtn = document.getElementById('enableBtn');
  if (enableBtn) {
    enableBtn.addEventListener('click', function () {
      hiddenField.value = 'on';
      form.submit();
    });
  }

  // หน้าเพิ่มมิเตอร์ใหม่: โชว์/ซ่อนช่อง "ระบบไฟฟ้า" ตามประเภทที่เลือก
  // (ไฟ = 8 เท่านั้นที่ใช้ระบบไฟฟ้า) ในหน้าแก้ไขไม่มี select นี้ เพราะประเภทล็อกไว้แล้ว
  const typeSelect = document.getElementById('meterTypeSelect');
  const phaseField = document.getElementById('phaseField');
  const meterNoInput = document.getElementById('meterNoInput');
  if (typeSelect && phaseField) {
    const phaseSelect = phaseField.querySelector('select[name="phase_type"]');
    const syncPhaseField = () => {
      const isElectric = typeSelect.value === '8';
      phaseField.classList.toggle('hidden', !isElectric);
      // ปิดใช้งานช่องไปด้วย ไม่ใช่แค่ซ่อน -- ช่องที่ซ่อนด้วย CSS ยังถูกส่งไปกับฟอร์ม
      // มิเตอร์น้ำไม่มีระบบไฟฟ้า การส่งค่านี้ไปจึงไม่มีความหมาย (view ก็ล้างเป็น None อยู่แล้ว)
      // และทำให้กล่องยืนยันก่อนบันทึกสรุปค่าที่ไม่ได้ใช้ขึ้นมาให้สับสน
      if (phaseSelect) phaseSelect.disabled = !isElectric;
    };
    typeSelect.addEventListener('change', syncPhaseField);
    syncPhaseField();
  }

  // ข้อความในช่องเลขเครื่องวัดต้องเปลี่ยนตามประเภท เพราะ sp_Contract_Meter_Save
  // auto-gen เลขให้เฉพาะ "เพิ่มใหม่ + มิเตอร์น้ำ + เว้นว่าง" (ได้ W001, W002, ...)
  // มิเตอร์ไฟไม่ gen ให้ ปล่อย NULL ไว้รอกรอกเลขจริงจากการไฟฟ้า
  // ถ้าใช้ข้อความเดียวกันทั้งสองประเภท จะมีประเภทหนึ่งที่ข้อความนั้นไม่จริง
  if (typeSelect && meterNoInput) {
    const syncMeterNoHint = () => {
      const key = typeSelect.value === '8' ? 'phElectric' : 'phWater';
      if (meterNoInput.dataset[key]) meterNoInput.placeholder = meterNoInput.dataset[key];
    };
    typeSelect.addEventListener('change', syncMeterNoHint);
    syncMeterNoHint();
  }

  // ---------------------------------------------------------------------------
  // ช่องเลือกพื้นที่ย่อย: เปลี่ยน <select> 468 ตัวเลือก ให้เป็น combobox ช่องเดียว
  // (พิมพ์ค้น -> รายการเด้งขึ้น -> คลิกหรือกด Enter เลือก)
  //
  // <select> ตัวเดิมยังเป็น form control จริงที่ส่งค่าไป server -- ที่นี่แค่ซ่อนมันไว้
  // แล้วเขียนค่ากลับลงไป ถ้า JS พังหรือถูกปิด ผู้ใช้ยังได้ dropdown ปกติที่ใช้งานได้
  // (select ที่ display:none ยังส่งค่าไปกับฟอร์ม ต่างจาก disabled ที่ไม่ส่ง)
  //
  // ทำไมไม่ใช้วิธีกรอง <option> ในตัว select: display:none บน <option> ใช้ไม่ได้
  // ทุกเบราว์เซอร์ (Safari ไม่สนใจ) และต่อให้กรองได้ ผู้ใช้ก็ยังต้องสลับไปมา 2 ช่อง
  //
  // การค้นหานี้อยู่ฝั่ง browser ทั้งหมด ไม่ได้ยิงไป server และ view ยัง validate
  // SubArea_id ที่ส่งมากับ master อีกชั้นเสมอ (save_standalone_meter)
  // ---------------------------------------------------------------------------
  const subareaSelect = document.getElementById('subareaSelect');
  const combo = document.getElementById('subareaCombo');
  const searchInput = document.getElementById('subareaSearch');
  const listBox = document.getElementById('subareaList');
  const clearBtn = document.getElementById('subareaClear');
  const hint = document.getElementById('subareaHint');

  if (subareaSelect && combo && searchInput && listBox) {
    // แสดงผลลัพธ์ไม่เกินจำนวนนี้ -- ถ้าไม่จำกัด การพิมพ์ตัวแรกจะต้องวาด 468 แถวทุกครั้ง
    // และรายการยาวเกินกว่าจะไล่อ่าน บอกจำนวนที่เหลือไว้ท้ายรายการแทน
    const MAX_RESULTS = 50;

    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

    // อ่านตัวเลือกทั้งหมดจาก select ครั้งเดียว -- ใช้ select เป็นแหล่งข้อมูลเดียว
    // ไม่ต้องส่ง JSON ซ้ำมาอีกชุด ข้อมูลจึงไม่มีทางหลุดจากกันระหว่าง 2 แหล่ง
    const items = [];
    Array.from(subareaSelect.querySelectorAll('optgroup')).forEach((og) => {
      Array.from(og.querySelectorAll('option')).forEach((o) => {
        const code = o.value;
        const name = norm(o.dataset.name);
        const group = norm(o.dataset.group || og.label);
        items.push({
          value: code,
          name: name,
          group: group,
          meters: parseInt(o.dataset.meters || '0', 10) || 0,
          inactive: o.dataset.inactive === '1',
          haystack: (code + ' ' + name + ' ' + group).toLowerCase(),
        });
      });
    });
    const byValue = {};
    items.forEach((it) => { byValue[it.value] = it; });

    let open = false;
    let activeIndex = -1;   // แถวที่ถูกไฮไลต์ด้วยคีย์บอร์ด
    let visible = [];       // ตัวเลือกที่กำลังแสดงอยู่จริง (เรียงตามที่เห็นบนจอ)

    // ซ่อน select ตัวจริงแล้วเปิด combobox -- ทำตอนนี้ (ไม่ใช่ใน HTML) เพื่อให้
    // คนที่ JS ไม่ทำงานเห็น select ปกติ ไม่ใช่เห็นหน้าเปล่าๆ ที่เลือกอะไรไม่ได้
    subareaSelect.classList.add('hidden');
    subareaSelect.setAttribute('tabindex', '-1');
    subareaSelect.setAttribute('aria-hidden', 'true');
    combo.classList.remove('hidden');

    const selectedItem = () => byValue[subareaSelect.value] || null;

    const labelFor = (it) => it.value + ' — ' + (it.name || '—');

    const syncHint = () => {
      const it = selectedItem();
      if (clearBtn) clearBtn.classList.toggle('hidden', !it);
      if (!hint) return;
      if (it) {
        hint.textContent = 'เลือกไว้: ' + it.value + (it.name ? ' (' + it.name + ')' : '');
      } else {
        hint.textContent = 'ยังไม่ได้เลือกพื้นที่';
      }
      hint.classList.toggle('text-brand-600', !!it);
      hint.classList.toggle('font-medium', !!it);
      hint.classList.toggle('text-gray-400', !it);
    };

    const closeList = () => {
      open = false;
      activeIndex = -1;
      listBox.classList.add('hidden');
      searchInput.setAttribute('aria-expanded', 'false');
      searchInput.removeAttribute('aria-activedescendant');
    };

    const setActive = (index) => {
      activeIndex = index;
      Array.from(listBox.querySelectorAll('[role="option"]')).forEach((el) => {
        const isActive = parseInt(el.dataset.index, 10) === index;
        el.classList.toggle('bg-brand-50', isActive);
        el.setAttribute('aria-selected', isActive ? 'true' : 'false');
        if (isActive) {
          searchInput.setAttribute('aria-activedescendant', el.id);
          // scrollIntoView แบบ nearest -- ไม่กระตุกหน้าจอเวลาเลื่อนด้วยลูกศร
          if (el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
        }
      });
    };

    const addRow = (tag, className, text) => {
      const el = document.createElement(tag);
      el.className = className;
      if (text) el.textContent = text;
      listBox.appendChild(el);
      return el;
    };

    const renderList = () => {
      const q = norm(searchInput.value).toLowerCase();
      const current = subareaSelect.value;
      // ถ้าข้อความในช่องเป็นชื่อของตัวที่เลือกไว้อยู่แล้ว (เพิ่งเลือกเสร็จ/โหลดหน้ามา)
      // ให้ถือว่าไม่ได้พิมพ์ค้นอะไร เพื่อให้กดเปิดแล้วเห็นรายการทั้งหมด ไม่ใช่เห็นแถวเดียว
      const isEchoOfSelection = !!current && q === labelFor(byValue[current]).toLowerCase();
      const query = isEchoOfSelection ? '' : q;

      const matched = query ? items.filter((it) => it.haystack.indexOf(query) !== -1) : items;
      visible = matched.slice(0, MAX_RESULTS);

      listBox.textContent = '';

      if (!matched.length) {
        addRow('li', 'px-3 py-3 text-sm text-gray-400 text-center', 'ไม่พบพื้นที่ที่ตรงกับคำค้น');
        listBox.classList.remove('hidden');
        searchInput.setAttribute('aria-expanded', 'true');
        open = true;
        activeIndex = -1;
        return;
      }

      let lastGroup = null;
      visible.forEach((it, index) => {
        if (it.group !== lastGroup) {
          lastGroup = it.group;
          const head = addRow(
            'li',
            'px-3 py-1.5 text-xs font-semibold text-gray-400 bg-gray-50 sticky top-0',
            it.group
          );
          head.setAttribute('role', 'presentation');
        }

        const li = addRow('li',
          'px-3 py-2 text-sm cursor-pointer flex items-start justify-between gap-3 hover:bg-brand-50');
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', it.value === current ? 'true' : 'false');
        li.id = 'subareaOpt-' + index;
        li.dataset.index = String(index);
        li.dataset.value = it.value;

        const left = document.createElement('span');
        left.className = 'min-w-0';
        const code = document.createElement('span');
        code.className = 'font-semibold text-gray-900';
        code.textContent = it.value;
        const name = document.createElement('span');
        name.className = 'block text-xs text-gray-500 truncate';
        name.textContent = it.name || '—';
        left.appendChild(code);
        left.appendChild(name);

        const right = document.createElement('span');
        right.className = 'shrink-0 flex items-center gap-1.5 pt-0.5';
        if (it.meters > 0) {
          const badge = document.createElement('span');
          badge.className = 'px-2 py-0.5 rounded-full text-xs font-medium bg-sky-50 text-sky-600';
          badge.textContent = 'มีมิเตอร์ ' + it.meters;
          right.appendChild(badge);
        }
        if (it.inactive) {
          const badge = document.createElement('span');
          badge.className = 'px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500';
          badge.textContent = 'ปิดใช้งาน';
          right.appendChild(badge);
        }
        if (it.value === current) {
          const badge = document.createElement('span');
          badge.className = 'px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-50 text-brand-600';
          badge.textContent = 'เลือกไว้';
          right.appendChild(badge);
        }

        li.appendChild(left);
        li.appendChild(right);
      });

      if (matched.length > visible.length) {
        addRow('li', 'px-3 py-2 text-xs text-gray-400 border-t border-gray-100 text-center',
          'แสดง ' + visible.length + ' จาก ' + matched.length + ' รายการ — พิมพ์เพิ่มเพื่อให้แคบลง')
          .setAttribute('role', 'presentation');
      }

      listBox.classList.remove('hidden');
      searchInput.setAttribute('aria-expanded', 'true');
      open = true;
      // ไฮไลต์ตัวที่เลือกไว้ถ้ามันอยู่ในผลลัพธ์ ไม่งั้นเริ่มที่แถวแรก
      const pos = visible.findIndex((it) => it.value === current);
      setActive(pos >= 0 ? pos : 0);
    };

    const pick = (value) => {
      const it = byValue[value];
      if (!it) return;
      subareaSelect.value = value;
      searchInput.value = labelFor(it);
      closeList();
      syncHint();
    };

    const clearSelection = () => {
      subareaSelect.value = '';
      searchInput.value = '';
      syncHint();
      closeList();
      searchInput.focus();
    };

    searchInput.addEventListener('input', renderList);
    searchInput.addEventListener('focus', renderList);
    // mousedown ไม่ใช่ click: ต้องเลือกให้เสร็จก่อน input จะ blur
    // ถ้าใช้ click แล้วมี handler อื่นปิดรายการตอน blur แถวจะหายไปก่อนที่ click จะยิง
    listBox.addEventListener('mousedown', (e) => {
      const row = e.target.closest('[role="option"]');
      if (!row) return;
      e.preventDefault();
      pick(row.dataset.value);
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!open) { renderList(); return; }
        if (!visible.length) return;
        const step = e.key === 'ArrowDown' ? 1 : -1;
        let next = activeIndex + step;
        if (next < 0) next = visible.length - 1;
        if (next >= visible.length) next = 0;
        setActive(next);
      } else if (e.key === 'Enter') {
        // กัน Enter ไป submit ฟอร์มตอนรายการเปิดอยู่ -- ให้หมายถึง "เลือกแถวนี้"
        if (open && activeIndex >= 0 && visible[activeIndex]) {
          e.preventDefault();
          pick(visible[activeIndex].value);
        }
      } else if (e.key === 'Escape') {
        if (open) { e.preventDefault(); closeList(); }
      } else if (e.key === 'Tab') {
        closeList();
      }
    });

    if (clearBtn) clearBtn.addEventListener('click', clearSelection);

    // คลิกที่อื่นนอกช่อง = ปิดรายการ และคืนข้อความในช่องให้ตรงกับค่าที่เลือกไว้จริง
    // (ถ้าผู้ใช้พิมพ์ค้างไว้แต่ไม่ได้เลือกอะไร จะเหลือข้อความที่ไม่ใช่ค่าจริงค้างอยู่ สับสน)
    document.addEventListener('mousedown', (e) => {
      if (combo.contains(e.target)) return;
      if (!open && !searchInput.value) return;
      closeList();
      const it = selectedItem();
      searchInput.value = it ? labelFor(it) : '';
    });

    // ตั้งค่าเริ่มต้นจากค่าที่ server ส่งมา (หน้าแก้ไข หรือ POST ที่ไม่ผ่าน)
    const initial = selectedItem();
    if (initial) searchInput.value = labelFor(initial);
    syncHint();
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
