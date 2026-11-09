// Component กลางสำหรับ <select> รายการสั้น
//
// วิธีใช้: เพิ่ม data-custom-select ให้ select เดิม โดย select ยังคงเป็น form control
// ที่ส่งค่าเข้า server ตามปกติ หาก JavaScript ไม่ทำงานจะเห็น native select เป็น fallback
(function () {
  const instances = [];

  const closeOthers = (except) => {
    instances.forEach((instance) => {
      if (instance !== except) instance.close();
    });
  };

  document.querySelectorAll('select[data-custom-select]').forEach((select, selectIndex) => {
    if (select.dataset.customSelectReady === '1') return;
    select.dataset.customSelectReady = '1';

    const componentId = select.id || `customSelect-${selectIndex}`;
    if (!select.id) select.id = componentId;

    const wrapper = document.createElement('div');
    wrapper.className = 'relative';
    wrapper.dataset.customSelectComponent = componentId;

    const button = document.createElement('button');
    button.type = 'button';
    button.id = `${componentId}-custom-button`;
    button.className = 'flex w-full items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-left text-base text-gray-700 transition-colors focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400 sm:py-2 sm:text-sm';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', select.dataset.customSelectLabel || 'เลือกรายการ');

    const valueLabel = document.createElement('span');
    valueLabel.className = 'min-w-0 truncate';

    const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('class', 'h-4 w-4 shrink-0 text-gray-500 transition-transform');
    chevron.setAttribute('fill', 'none');
    chevron.setAttribute('viewBox', '0 0 24 24');
    chevron.setAttribute('stroke', 'currentColor');
    chevron.setAttribute('stroke-width', '2');
    chevron.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6"></path>';

    button.appendChild(valueLabel);
    button.appendChild(chevron);

    // label ที่เดิมชี้ไปยัง native select ต้องชี้มาที่ปุ่มที่มองเห็นแทน
    // ถ้า JavaScript ไม่ทำงาน label จะยังชี้ select เดิมตามปกติ
    document.querySelectorAll(`label[for="${componentId}"]`).forEach((label) => {
      label.htmlFor = button.id;
    });

    const list = document.createElement('ul');
    list.id = `${componentId}-custom-list`;
    list.setAttribute('role', 'listbox');
    list.setAttribute('aria-label', select.dataset.customSelectLabel || 'เลือกรายการ');
    list.className = 'fixed z-50 hidden overflow-y-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg';
    list.style.zIndex = '1000';
    button.setAttribute('aria-controls', list.id);

    let open = false;
    let rows = [];

    const selectableRows = () => rows.filter((row) => !row.option.disabled);

    const sync = () => {
      const selected = select.options[select.selectedIndex];
      valueLabel.textContent = selected ? selected.textContent.trim() : 'เลือกรายการ';
      button.disabled = select.disabled;
      rows.forEach((row) => {
        const isSelected = row.option.selected;
        row.element.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        row.element.classList.toggle('bg-brand-50', isSelected);
        row.element.classList.toggle('font-semibold', isSelected);
        row.element.classList.toggle('text-brand-700', isSelected);
      });
      if (select.disabled) close();
    };

    const close = () => {
      open = false;
      list.classList.add('hidden');
      button.setAttribute('aria-expanded', 'false');
      chevron.classList.remove('rotate-180');
    };

    const focusSelected = () => {
      const selectedRow = rows.find((row) => row.option.selected && !row.option.disabled);
      const firstRow = selectableRows()[0];
      const target = selectedRow || firstRow;
      if (target) target.element.focus();
    };

    // รายการถูกย้ายไปไว้ใต้ body เพื่อไม่ให้ overflow ของ Card/Table ตัดทิ้ง
    // ตำแหน่งจึงต้องคำนวณจากปุ่มทุกครั้งที่เปิด และเปิดขึ้นด้านบนเมื่อพื้นที่ล่างไม่พอ
    const positionList = () => {
      const rect = button.getBoundingClientRect();
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = document.documentElement.clientHeight;
      const gap = 4;
      const edge = 8;
      const desiredMaxHeight = 240;
      const spaceBelow = viewportHeight - rect.bottom - edge;
      const spaceAbove = rect.top - edge;
      const openAbove = spaceBelow < desiredMaxHeight && spaceAbove > spaceBelow;
      const availableHeight = Math.max(120, (openAbove ? spaceAbove : spaceBelow) - gap);
      const menuWidth = Math.min(rect.width, viewportWidth - (edge * 2));
      const left = Math.max(edge, Math.min(rect.left, viewportWidth - menuWidth - edge));

      list.style.position = 'fixed';
      list.style.left = `${left}px`;
      list.style.width = `${menuWidth}px`;
      list.style.maxHeight = `${Math.min(desiredMaxHeight, availableHeight)}px`;

      if (openAbove) {
        list.style.top = `${Math.max(edge, rect.top - list.offsetHeight - gap)}px`;
      } else {
        list.style.top = `${rect.bottom + gap}px`;
      }
    };

    const show = () => {
      if (select.disabled) return;
      closeOthers(instance);
      open = true;
      list.style.visibility = 'hidden';
      list.classList.remove('hidden');
      positionList();
      list.style.visibility = '';
      button.setAttribute('aria-expanded', 'true');
      chevron.classList.add('rotate-180');
      focusSelected();
    };

    const pick = (row) => {
      if (!row || row.option.disabled) return;
      select.value = row.option.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      sync();
      close();
      button.focus();
    };

    const addOption = (option) => {
      const item = document.createElement('li');
      item.setAttribute('role', 'option');
      item.tabIndex = -1;
      item.textContent = option.textContent.trim();
      item.className = option.disabled
        ? 'cursor-not-allowed px-3 py-2 text-sm text-gray-300'
        : 'cursor-pointer px-3 py-2 text-sm text-gray-700 outline-none hover:bg-brand-50 hover:text-brand-700 focus:bg-brand-50 focus:text-brand-700';
      const row = { option: option, element: item };
      rows.push(row);
      item.addEventListener('click', () => pick(row));
      list.appendChild(item);
    };

    Array.from(select.children).forEach((child) => {
      if (child.tagName === 'OPTGROUP') {
        const heading = document.createElement('li');
        heading.setAttribute('role', 'presentation');
        heading.className = 'bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-400';
        heading.textContent = child.label;
        list.appendChild(heading);
        Array.from(child.children).forEach(addOption);
      } else if (child.tagName === 'OPTION') {
        addOption(child);
      }
    });

    const instance = {
      close: close,
      contains: (target) => wrapper.contains(target) || list.contains(target),
    };
    instances.push(instance);

    button.addEventListener('click', () => {
      if (open) close();
      else show();
    });

    button.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        show();
      } else if (event.key === 'Escape' && open) {
        event.preventDefault();
        close();
      }
    });

    list.addEventListener('keydown', (event) => {
      const currentElement = event.target.closest('[role="option"]');
      const enabled = selectableRows();
      const currentIndex = enabled.findIndex((row) => row.element === currentElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!enabled.length) return;
        const step = event.key === 'ArrowDown' ? 1 : -1;
        enabled[(currentIndex + step + enabled.length) % enabled.length].element.focus();
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        pick(enabled[currentIndex]);
      } else if (event.key === 'Escape' || event.key === 'Tab') {
        close();
        if (event.key === 'Escape') {
          event.preventDefault();
          button.focus();
        }
      }
    });

    select.addEventListener('change', sync);
    select.addEventListener('custom-select:refresh', sync);

    // รองรับหน้าที่เปิด/ปิด select ตาม checkbox หรือสถานะอื่นภายหลังโหลดหน้า
    new MutationObserver(sync).observe(select, {
      attributes: true,
      attributeFilter: ['disabled'],
    });

    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(button);
    document.body.appendChild(list);
    select.classList.add('hidden');
    select.setAttribute('tabindex', '-1');
    select.setAttribute('aria-hidden', 'true');
    sync();
  });

  document.addEventListener('mousedown', (event) => {
    instances.forEach((instance) => {
      if (!instance.contains(event.target)) instance.close();
    });
  });

  // ถ้าหน้าจอหรือจุดเลื่อนของหน้าเปลี่ยน ให้ปิดก่อนเพื่อไม่ให้รายการลอยผิดตำแหน่ง
  window.addEventListener('resize', () => instances.forEach((instance) => instance.close()));
  window.addEventListener('scroll', () => instances.forEach((instance) => instance.close()), { passive: true });
})();
