/* WebCheck-AI – Scan Configuration Page */
'use strict';

// Show/hide explore section based on mode
document.querySelectorAll('input[name="mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    document.getElementById('explore-section').style.display =
      document.querySelector('input[name="mode"]:checked').value === 'explore' ? '' : 'none';
  });
});

// Screenshot dependency logic
(function () {
  const ssEnabled    = document.getElementById('ss_enabled');
  const ssOnError    = document.getElementById('ss_on_error');
  const ssOnInteract = document.getElementById('ss_on_interaction');
  const ssFullPage   = document.getElementById('ss_full_page');
  if (!ssEnabled) return;

  function syncScreenshots() {
    const enabled = ssEnabled.checked;
    const onError = ssOnError.checked;

    ssOnError.disabled    = !enabled;
    ssFullPage.disabled   = !enabled;
    ssOnInteract.disabled = !enabled || !onError;

    if (!enabled) {
      ssOnError.checked    = false;
      ssFullPage.checked   = false;
      ssOnInteract.checked = false;
    }
    if (!onError) {
      ssOnInteract.checked = false;
    }
  }

  ssEnabled.addEventListener('change', syncScreenshots);
  ssOnError.addEventListener('change', syncScreenshots);
  syncScreenshots();
})();

// LLM provider → model options + live Ollama status banner
(function () {
  const MODELS = {
    anthropic: [
      { value: '',                          label: 'Default (claude-sonnet-4-6)' },
      { value: 'claude-sonnet-4-6',         label: 'claude-sonnet-4-6' },
      { value: 'claude-opus-4-6',           label: 'claude-opus-4-6' },
      { value: 'claude-haiku-4-5-20251001', label: 'claude-haiku-4-5-20251001' },
    ],
    openai: [
      { value: '',            label: 'Default (gpt-4o)' },
      { value: 'gpt-4o',      label: 'gpt-4o' },
      { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
      { value: 'gpt-4-turbo', label: 'gpt-4-turbo' },
      { value: 'o1',          label: 'o1' },
      { value: 'o1-mini',     label: 'o1-mini' },
    ],
    ollama: [
      { value: '', label: 'Default (qwen2.5:3b)' },
      { value: 'qwen2.5:3b', label: 'qwen2.5:3b' },
    ],
  };

  let aiStatus = window.__webcheckAIStatus || null;

  function renderBanner(provider) {
    const banner = document.getElementById('ai-provider-banner');
    const hint = document.getElementById('llm_key_hint');
    if (!banner) return;

    if (!aiStatus) {
      banner.className = 'ai-banner';
      banner.textContent = 'Checking local Ollama and AI provider availability…';
      return;
    }

    const ollama = aiStatus.ollama || {};
    const providers = aiStatus.providers || {};

    if (provider === 'ollama') {
      if (ollama.available) {
        const installed = (ollama.models || []).join(', ') || 'none pulled';
        banner.className = 'ai-banner ai-banner-ok';
        banner.innerHTML = `<strong>Local Ollama Ready</strong> — Running at <code>${escapeHtml(ollama.host)}</code> · Installed models: <code>${escapeHtml(installed)}</code>`;
      } else {
        banner.className = 'ai-banner ai-banner-warn';
        banner.innerHTML = `<strong>Ollama Not Reachable</strong> — Will use safe rule-based verification fallback unless Ollama is running at <code>${escapeHtml(ollama.host || 'http://localhost:11434')}</code>.`;
      }
      if (hint) hint.innerHTML = 'Runs locally via Ollama. No API key required; safe rule-based fallback if unavailable.';
    } else if (provider === 'anthropic') {
      const ok = providers.anthropic?.configured;
      banner.className = ok ? 'ai-banner ai-banner-ok' : 'ai-banner ai-banner-warn';
      banner.innerHTML = ok
        ? '<strong>Anthropic Configured</strong> — <code>ANTHROPIC_API_KEY</code> detected in server environment.'
        : '<strong>ANTHROPIC_API_KEY Not Set</strong> — Set it in the environment for Claude planning/verification, otherwise rule-based fallback applies.';
      if (hint) hint.innerHTML = 'Requires <code>ANTHROPIC_API_KEY</code> environment variable.';
    } else if (provider === 'openai') {
      const ok = providers.openai?.configured;
      banner.className = ok ? 'ai-banner ai-banner-ok' : 'ai-banner ai-banner-warn';
      banner.innerHTML = ok
        ? '<strong>OpenAI Configured</strong> — <code>OPENAI_API_KEY</code> detected in server environment.'
        : '<strong>OPENAI_API_KEY Not Set</strong> — Set it in the environment for OpenAI planning/verification, otherwise rule-based fallback applies.';
      if (hint) hint.innerHTML = 'Requires <code>OPENAI_API_KEY</code> environment variable.';
    }
  }

  function updateLLMOptions() {
    const providerSel = document.getElementById('llm_provider');
    const modelSel = document.getElementById('ai_model');
    if (!providerSel || !modelSel) return;

    const provider = providerSel.value;
    const previousVal = modelSel.value;
    let models = [...(MODELS[provider] || [])];

    if (provider === 'ollama' && aiStatus?.ollama?.models?.length) {
      const seen = new Set(models.map(m => m.value));
      for (const installedName of aiStatus.ollama.models) {
        if (!seen.has(installedName)) {
          models.push({ value: installedName, label: `${installedName} (installed)` });
          seen.add(installedName);
        }
      }
    }

    modelSel.innerHTML = models
      .map(m => `<option value="${escapeHtml(m.value)}">${escapeHtml(m.label)}</option>`)
      .join('');

    if (previousVal && models.some(m => m.value === previousVal)) {
      modelSel.value = previousVal;
    }

    renderBanner(provider);
  }

  window.addEventListener('webcheck:ai-status', (e) => {
    aiStatus = e.detail;
    const providerSel = document.getElementById('llm_provider');
    if (providerSel && !aiStatus.ollama?.available && providerSel.value === 'ollama') {
      if (aiStatus.providers?.openai?.configured) {
        providerSel.value = 'openai';
      } else if (aiStatus.providers?.anthropic?.configured) {
        providerSel.value = 'anthropic';
      }
    }
    updateLLMOptions();
  });

  document.getElementById('llm_provider')?.addEventListener('change', updateLLMOptions);
  updateLLMOptions();
})();

// Pool size — fetch current value and wire up the Apply button
(function () {
  const input = document.getElementById('pool-size-input');
  const btn   = document.getElementById('update-pool-btn');
  const msg   = document.getElementById('pool-size-msg');
  if (!input || !btn || !msg) return;

  fetch('/api/server-config')
    .then(r => r.json())
    .then(cfg => { input.value = cfg.pool_size; input.max = cfg.pool_size_max || 8; })
    .catch(() => {});

  btn.addEventListener('click', async () => {
    const newSize = parseInt(input.value, 10);
    btn.disabled = true;
    msg.textContent = 'Updating…';
    try {
      const res  = await fetch('/api/server-config', {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ pool_size: newSize }),
      });
      const data = await res.json();
      if (res.ok) {
        input.value    = data.pool_size;
        msg.textContent = `Pool size set to ${data.pool_size}.`;
      } else {
        msg.textContent = `Error: ${data.error || 'Update failed'}`;
      }
    } catch (err) {
      msg.textContent = `Error: ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
})();

// Load instructions from a local text/markdown file into the textarea
document.getElementById('instructions_file')?.addEventListener('change', function () {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('instructions').value = e.target.result;
  };
  reader.readAsText(file);
  this.value = '';
});
