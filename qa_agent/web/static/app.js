/* WebCheck-AI – client-side JS */
'use strict';

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Global Navbar AI Status Pill ──────────────────────────────────────────────
(function () {
  const pill = document.getElementById('nav-ai-status');
  if (!pill) return;

  fetch('/api/ai/status')
    .then(r => r.json())
    .then(data => {
      window.__webcheckAIStatus = data;
      window.dispatchEvent(new CustomEvent('webcheck:ai-status', { detail: data }));

      const ollama = data.ollama || {};
      const label = pill.querySelector('.status-label');
      pill.classList.remove('ai-status-loading');
      if (ollama.available) {
        pill.classList.add('ai-status-online');
        const modelLabel = ollama.has_default_model
          ? ollama.default_model
          : (ollama.models && ollama.models[0]) || 'connected';
        if (label) label.textContent = `Ollama · ${modelLabel}`;
        pill.title = `Local Ollama online (${(ollama.models || []).join(', ') || 'no models pulled'})`;
      } else {
        pill.classList.add('ai-status-fallback');
        if (label) label.textContent = 'Rule-Based Fallback';
        pill.title = `Local Ollama offline (${ollama.error || 'not running'})`;
      }
    })
    .catch(() => {
      pill.classList.remove('ai-status-loading');
      pill.classList.add('ai-status-fallback');
      const label = pill.querySelector('.status-label');
      if (label) label.textContent = 'AI Status Unknown';
    });
})();

// ── Form submission & config helpers ──────────────────────────────────────────
(function () {
  const form = document.getElementById('run-form');
  if (!form) return;

  const rerunConfig = sessionStorage.getItem('qa_rerun_config');
  if (rerunConfig) {
    sessionStorage.removeItem('qa_rerun_config');
    try { applyConfig(JSON.parse(rerunConfig)); } catch (_) {}
  }

  populatePresets();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    const errEl = document.getElementById('form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Starting Scan…';

    const body = collectFormData(form);
    if (!body.urls.length) {
      errEl.textContent = 'Please enter at least one target URL.';
      errEl.style.display = '';
      btn.disabled = false;
      btn.textContent = 'Start Scan';
      return;
    }

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start scan');
      window.location.href = '/run/' + data.job_id;
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = '';
      btn.disabled = false;
      btn.textContent = 'Start Scan';
    }
  });

  document.getElementById('save-preset-btn')?.addEventListener('click', () => {
    const name = prompt('Preset name:');
    if (!name || !name.trim()) return;
    const presets = getPresets();
    presets[name.trim()] = collectFormData(form);
    savePresets(presets);
    populatePresets();
  });

  document.getElementById('preset-select')?.addEventListener('change', function () {
    const presets = getPresets();
    if (this.value && presets[this.value]) {
      applyConfig(presets[this.value]);
    }
    this.value = '';
  });

  document.getElementById('reset-btn')?.addEventListener('click', () => {
    form.reset();
    document.getElementById('explore-section').style.display = 'none';
    document.getElementById('llm_provider')?.dispatchEvent(new Event('change'));
    document.getElementById('ss_enabled')?.dispatchEvent(new Event('change'));
  });

  document.getElementById('export-config-btn')?.addEventListener('click', () => {
    const cfg = collectFormData(form);
    const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'webcheck-ai-config.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });

  document.getElementById('import-config-input')?.addEventListener('change', function () {
    const file = this.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
      try {
        applyConfig(JSON.parse(e.target.result));
      } catch (_) {
        alert('Invalid config JSON file.');
      }
    };
    reader.readAsText(file);
    this.value = '';
  });
})();

function collectFormData(form) {
  const fd = new FormData(form);
  const urlsRaw = (fd.get('urls') || '').split('\n').map(u => u.trim()).filter(Boolean);
  const mode = fd.get('mode') || 'focused';
  const outputFormats = fd.getAll('output_formats');

  return {
    urls: urlsRaw,
    mode,
    output_formats: outputFormats.length ? outputFormats : ['console', 'markdown', 'json'],
    output_dir: (fd.get('output_dir') || '').trim() || null,
    headless: !!fd.get('headless'),
    workers: parseInt(fd.get('workers') || '1', 10),
    viewport_width: parseInt(fd.get('viewport_width') || '1280', 10),
    viewport_height: parseInt(fd.get('viewport_height') || '720', 10),
    timeout: parseInt(fd.get('timeout') || '30000', 10),
    max_depth: parseInt(fd.get('max_depth') || '3', 10),
    max_pages: parseInt(fd.get('max_pages') || '100', 10),
    max_interactions_per_page: parseInt(fd.get('max_interactions_per_page') || '50', 10),
    test_keyboard: !!fd.get('test_keyboard'),
    test_mouse: !!fd.get('test_mouse'),
    test_forms: !!fd.get('test_forms'),
    test_accessibility: !!fd.get('test_accessibility'),
    test_console_errors: !!fd.get('test_console_errors'),
    test_network_errors: !!fd.get('test_network_errors'),
    test_wcag_compliance: !!fd.get('test_wcag_compliance'),
    same_domain_only: !!fd.get('same_domain_only'),
    ignore_patterns: (fd.get('ignore_patterns') || '').split('\n').map(s => s.trim()).filter(Boolean),
    instructions: (fd.get('instructions') || '').trim() || null,
    llm_provider: fd.get('llm_provider') || 'ollama',
    ai_model: fd.get('ai_model') || '',
    use_plan_cache: !!fd.get('use_plan_cache'),
    generate_summary: !!fd.get('generate_summary'),
    screenshots: {
      enabled: !!fd.get('screenshots_enabled'),
      on_error: !!fd.get('screenshots_on_error'),
      on_interaction: !!fd.get('screenshots_on_interaction'),
      full_page: !!fd.get('screenshots_full_page'),
    },
    recording: {
      enabled: !!fd.get('recording_enabled'),
    },
    auth: {
      auth_url: fd.get('auth_url') || null,
      username: fd.get('auth_username') || null,
      password: fd.get('auth_password') || null,
      username_selector: fd.get('auth_username_selector') || null,
      password_selector: fd.get('auth_password_selector') || null,
      submit_selector: fd.get('auth_submit_selector') || null,
      cookies: fd.get('auth_cookies') || null,
      headers: fd.get('auth_headers') || null,
    },
  };
}

function applyConfig(cfg) {
  const form = document.getElementById('run-form');
  if (!form || !cfg) return;

  if (Array.isArray(cfg.urls)) form.querySelector('#urls').value = cfg.urls.join('\n');
  if (cfg.mode) {
    const radio = form.querySelector(`input[name="mode"][value="${cfg.mode}"]`);
    if (radio) {
      radio.checked = true;
      document.getElementById('explore-section').style.display =
        cfg.mode === 'explore' ? '' : 'none';
    }
  }
  if (Array.isArray(cfg.output_formats)) {
    form.querySelectorAll('input[name="output_formats"]').forEach(cb => {
      cb.checked = cfg.output_formats.includes(cb.value);
    });
  }

  setCheck(form, 'headless', cfg.headless !== false);
  setNum(form, 'workers', cfg.workers);
  setNum(form, 'viewport_width', cfg.viewport_width);
  setNum(form, 'viewport_height', cfg.viewport_height);
  setNum(form, 'timeout', cfg.timeout);
  setNum(form, 'max_depth', cfg.max_depth);
  setNum(form, 'max_pages', cfg.max_pages);
  setNum(form, 'max_interactions_per_page', cfg.max_interactions_per_page);

  for (const flag of [
    'test_keyboard', 'test_mouse', 'test_forms', 'test_accessibility',
    'test_console_errors', 'test_network_errors', 'test_wcag_compliance',
    'same_domain_only', 'use_plan_cache', 'generate_summary',
  ]) {
    if (cfg[flag] !== undefined) setCheck(form, flag, cfg[flag]);
  }

  if (Array.isArray(cfg.ignore_patterns)) {
    const ig = form.querySelector('#ignore_patterns');
    if (ig) ig.value = cfg.ignore_patterns.join('\n');
  }
  if (cfg.instructions !== undefined) {
    const inst = form.querySelector('#instructions');
    if (inst) inst.value = cfg.instructions || '';
  }

  const outputDirEl = form.querySelector('#output_dir');
  if (outputDirEl && cfg.output_dir) outputDirEl.value = cfg.output_dir;

  if (cfg.llm_provider) {
    const provSel = form.querySelector('#llm_provider');
    if (provSel) {
      provSel.value = cfg.llm_provider;
      provSel.dispatchEvent(new Event('change'));
    }
  }
  if (cfg.ai_model !== undefined) {
    const modelSel = form.querySelector('#ai_model');
    if (modelSel && cfg.ai_model) {
      if (!Array.from(modelSel.options).some(o => o.value === cfg.ai_model)) {
        const opt = document.createElement('option');
        opt.value = cfg.ai_model;
        opt.textContent = cfg.ai_model;
        modelSel.appendChild(opt);
      }
      modelSel.value = cfg.ai_model;
    }
  }

  if (cfg.screenshots) {
    setCheck(form, 'screenshots_enabled', cfg.screenshots.enabled !== false);
    setCheck(form, 'screenshots_on_error', cfg.screenshots.on_error !== false);
    setCheck(form, 'screenshots_on_interaction', !!cfg.screenshots.on_interaction);
    setCheck(form, 'screenshots_full_page', !!cfg.screenshots.full_page);
    document.getElementById('ss_enabled')?.dispatchEvent(new Event('change'));
  }
  if (cfg.recording) {
    setCheck(form, 'recording_enabled', !!cfg.recording.enabled);
  }
  if (cfg.auth) {
    for (const key of ['auth_url', 'username', 'password', 'username_selector', 'password_selector', 'submit_selector', 'cookies', 'headers']) {
      const inputName = key === 'auth_url' ? 'auth_url' : `auth_${key}`;
      const el = form.querySelector(`[name="${inputName}"]`);
      if (el && cfg.auth[key] !== undefined && cfg.auth[key] !== null) {
        el.value = typeof cfg.auth[key] === 'string' ? cfg.auth[key] : JSON.stringify(cfg.auth[key]);
      }
    }
  }
}

function setCheck(form, name, val) {
  const el = form.querySelector(`[name="${name}"]`);
  if (el) el.checked = !!val;
}

function setNum(form, name, val) {
  const el = form.querySelector(`[name="${name}"]`);
  if (el && val !== undefined && val !== null) el.value = val;
}

function getPresets() {
  try { return JSON.parse(localStorage.getItem('qa_presets') || '{}'); } catch (_) { return {}; }
}

function savePresets(presets) {
  localStorage.setItem('qa_presets', JSON.stringify(presets));
}

function populatePresets() {
  const sel = document.getElementById('preset-select');
  if (!sel) return;
  const presets = getPresets();
  const names = Object.keys(presets);
  while (sel.options.length > 1) sel.remove(1);
  names.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
  sel.style.display = names.length ? '' : 'none';
}
