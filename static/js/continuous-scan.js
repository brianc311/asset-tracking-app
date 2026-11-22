(function () {
  const MODES = ['mac', 'serial', 'pair'];
  let mode = 'mac';
  let rows = [];
  let pairSerial = '';
  let lastText = '';
  let scanner = null;

  function $(id) {
    return document.getElementById(id);
  }

  function setMode(next) {
    if (rows.length && next !== mode) {
      window.alert('Clear the scanned list before changing what you scan.');
      return;
    }
    mode = next;
    const input = $('continuous-mode');
    if (input) input.value = mode;
    document.querySelectorAll('[data-continuous-mode]').forEach((button) => {
      const selected = button.getAttribute('data-continuous-mode') === mode;
      button.classList.toggle('btn-primary', selected);
      button.classList.toggle('btn-secondary', !selected);
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    syncSharedFields();
  }

  function syncSharedFields() {
    const serialWrap = $('continuous-shared-serial');
    const macWrap = $('continuous-shared-mac');
    if (serialWrap) serialWrap.hidden = mode !== 'mac';
    if (macWrap) macWrap.hidden = mode !== 'serial';
  }

  function renderList(target) {
    if (!target) return;
    target.replaceChildren();
    rows.forEach((row, index) => {
      const item = document.createElement('li');
      const label = document.createElement('span');
      const parts = [];
      if (row.serial) parts.push('Serial ' + row.serial);
      if (row.mac) parts.push('MAC ' + row.mac);
      label.textContent = parts.join(' — ') || 'Empty';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-secondary';
      remove.style.marginLeft = '0.5rem';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => {
        rows.splice(index, 1);
        if (!rows.length) pairSerial = '';
        renderAll();
      });
      item.append(label, remove);
      target.append(item);
    });
  }

  function renderAll() {
    const field = $('continuous-rows');
    if (field) field.value = JSON.stringify(rows);
    renderList($('continuous-preview'));
    renderList($('continuous-live-list'));
    const form = $('continuous-finish-form');
    if (form) form.hidden = rows.length === 0;
    const hint = $('continuous-live-hint');
    if (hint) {
      if (mode === 'pair' && pairSerial) {
        hint.textContent = 'Row ' + (rows.length + 1) + ': scan the MAC for serial ' + pairSerial + '.';
      } else if (mode === 'pair') {
        hint.textContent = 'Row ' + (rows.length + 1) + ': scan the serial number.';
      } else {
        hint.textContent = rows.length + ' scanned. Point the camera at the next code.';
      }
    }
  }

  function accept(value) {
    if (!value || value === lastText) return;
    lastText = value;
    if (mode === 'mac') {
      rows.push({ serial: '', mac: value });
    } else if (mode === 'serial') {
      rows.push({ serial: value, mac: '' });
    } else if (pairSerial) {
      rows.push({ serial: pairSerial, mac: value });
      pairSerial = '';
    } else {
      pairSerial = value;
    }
    renderAll();
  }

  function ensureModal() {
    if ($('continuous-scan-modal')) return;
    document.body.insertAdjacentHTML('beforeend', `
      <div id="continuous-scan-modal" class="modal-overlay" role="dialog" aria-modal="true">
        <div class="modal-box" style="max-width:560px">
          <h3 class="modal-title">Continuous scan</h3>
          <p class="modal-body" id="continuous-live-hint">Point the camera at the next code.</p>
          <div id="continuous-scan-reader" style="width:100%;min-height:220px;margin-bottom:1rem"></div>
          <ol id="continuous-live-list" style="margin:0 0 1rem;padding-left:1.25rem"></ol>
          <div class="modal-actions">
            <button type="button" class="btn btn-primary" id="continuous-scan-done">Done</button>
          </div>
        </div>
      </div>
    `);
    $('continuous-scan-done').addEventListener('click', closeScanner);
  }

  async function stopScanner() {
    if (!scanner) return;
    try { await scanner.stop(); } catch (_) {}
    try { scanner.clear(); } catch (_) {}
    scanner = null;
  }

  async function closeScanner() {
    if (pairSerial) {
      rows.push({ serial: pairSerial, mac: '' });
      pairSerial = '';
    }
    await stopScanner();
    $('continuous-scan-modal')?.classList.remove('open');
    lastText = '';
    renderAll();
  }

  async function openScanner() {
    if (!window.isSecureContext) {
      await AppModal.alert('HTTPS required', 'Camera scanning on your phone requires https://.');
      return;
    }
    if (typeof Html5Qrcode === 'undefined') {
      await AppModal.alert('Scanner unavailable', 'Barcode library did not load. Refresh the page and try again.');
      return;
    }
    ensureModal();
    renderAll();
    $('continuous-scan-modal').classList.add('open');
    await stopScanner();
    scanner = new Html5Qrcode('continuous-scan-reader');
    try {
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        (decodedText) => accept((decodedText || '').trim()),
        () => {}
      );
    } catch (err) {
      await closeScanner();
      let msg = err.message || 'Could not access camera.';
      if (msg.includes('NotAllowed') || msg.includes('Permission')) {
        msg = 'Camera permission denied. Allow camera access in browser settings.';
      }
      await AppModal.alert('Camera Error', msg);
    }
  }

  function seedFromField() {
    const field = $('continuous-rows');
    if (!field || !field.value) return;
    try {
      const parsed = JSON.parse(field.value);
      if (Array.isArray(parsed)) rows = parsed;
    } catch (_) {}
    renderAll();
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('continuous-scan-start')) return;
    document.querySelectorAll('[data-continuous-mode]').forEach((button) => {
      button.addEventListener('click', () => setMode(button.getAttribute('data-continuous-mode')));
    });
    const postedMode = ($('continuous-mode') || {}).value;
    setMode(MODES.includes(postedMode) ? postedMode : 'mac');
    seedFromField();
    $('continuous-scan-start').addEventListener('click', openScanner);
    const clear = $('continuous-scan-clear');
    if (clear) {
      clear.addEventListener('click', () => {
        rows = [];
        pairSerial = '';
        lastText = '';
        renderAll();
      });
    }
  });
})();
