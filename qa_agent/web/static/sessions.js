/* WebCheck-AI – Sessions Directory */
'use strict';

(function () {
  const container = document.getElementById('sessions-container');
  const activeJobsContainer = document.getElementById('active-jobs-container');
  const search = document.getElementById('search');
  const statusFilter = document.getElementById('status-filter');
  const refreshBtn = document.getElementById('refresh-sessions-btn');
  const overviewEl = document.getElementById('sessions-overview');

  if (!container) return;

  const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];
  let allSessions = [];

  function severityBadge(sev, count) {
    return count > 0
      ? `<span class="badge badge-${sev}" title="${sev}">${count} ${sev}</span>`
      : '';
  }

  function formatDuration(secs) {
    if (secs === null || secs === undefined) return '—';
    if (secs < 60) return Math.round(secs) + 's';
    return Math.floor(secs / 60) + 'm ' + Math.round(secs % 60) + 's';
  }

  function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
  }

  function updateOverview(sessions) {
    if (!overviewEl) return;
    if (!sessions.length) {
      overviewEl.style.display = 'none';
      return;
    }
    const domains = new Set(sessions.map(s => s.domain));
    const totalFindings = sessions.reduce((acc, s) => acc + (s.total_findings || 0), 0);
    const verifiedFindings = sessions.reduce(
      (acc, s) => acc + (s.verification_summary?.verified || 0),
      0
    );

    document.getElementById('ov-total-sessions').textContent = sessions.length;
    document.getElementById('ov-total-domains').textContent = domains.size;
    document.getElementById('ov-total-findings').textContent = totalFindings;
    document.getElementById('ov-verified-findings').textContent = verifiedFindings;
    overviewEl.style.display = '';
  }

  function renderSessions(sessions) {
    if (!sessions.length) {
      container.innerHTML = `<div class="card empty-state">
        <p>No matching scan sessions found. <a href="/">Launch a new scan</a> to get started.</p>
      </div>`;
      return;
    }

    const grouped = {};
    sessions.forEach(s => {
      (grouped[s.domain] = grouped[s.domain] || []).push(s);
    });

    let html = '';
    Object.keys(grouped).sort().forEach(domain => {
      const safeDomain = escapeHtml(domain);
      html += `<details class="domain-group" open>
        <summary class="domain-title">
          <span class="domain-name">${safeDomain}</span>
          <span class="domain-count">${grouped[domain].length} scan${grouped[domain].length !== 1 ? 's' : ''}</span>
        </summary>
        <div class="session-list">`;

      grouped[domain].forEach(s => {
        const severityBadges = SEVERITY_ORDER
          .map(sev => severityBadge(sev, s.findings_by_severity?.[sev] || 0))
          .join('');
        const urls = (s.urls || []).map(u => `<span class="url-tag">${escapeHtml(u)}</span>`).join('');
        const vs = s.verification_summary || {};
        const verifiedBadge = vs.verified > 0
          ? `<span class="badge badge-v-verified">${vs.verified} verified</span>`
          : '';
        const providerBadge = s.llm_provider
          ? `<span class="source-pill">${escapeHtml(s.llm_provider)}${s.ai_model ? ' · ' + escapeHtml(s.ai_model) : ''}</span>`
          : '';

        html += `<a class="session-card" href="/session/${encodeURIComponent(s.domain)}/${encodeURIComponent(s.session_id)}">
          <div class="session-card-main">
            <code class="session-id">${escapeHtml(s.session_id)}</code>
            <span class="badge badge-status-${escapeHtml(s.status || 'passed')}">${escapeHtml((s.status || 'passed').replace(/_/g, ' '))}</span>
            ${providerBadge}
            <div class="session-urls">${urls}</div>
          </div>
          <div class="session-card-meta">
            <span class="text-muted">${formatDate(s.start_time)}</span>
            <span class="text-muted">${formatDuration(s.duration_seconds)}</span>
            <span class="findings-count ${s.total_findings > 0 ? 'has-findings' : ''}">${s.total_findings} finding${s.total_findings !== 1 ? 's' : ''}</span>
            ${verifiedBadge}
            <div class="severity-badges">${severityBadges}</div>
          </div>
        </a>`;
      });

      html += '</div></details>';
    });

    container.innerHTML = html;
  }

  function applyClientFilters() {
    const query = (search?.value || '').trim().toLowerCase();
    const st = statusFilter?.value || 'all';
    let filtered = allSessions;

    if (st !== 'all') {
      filtered = filtered.filter(s => s.status === st);
    }
    if (query) {
      filtered = filtered.filter(s =>
        (s.domain || '').toLowerCase().includes(query) ||
        (s.session_id || '').toLowerCase().includes(query) ||
        (s.urls || []).some(u => u.toLowerCase().includes(query))
      );
    }
    renderSessions(filtered);
  }

  const STATUS_LABELS = {
    queued: 'Queued',
    running: 'Running',
    stopping: 'Stopping',
    stopped: 'Stopped',
    completed: 'Completed',
    failed: 'Failed',
  };

  function renderActiveJobs(jobs) {
    const active = jobs.filter(j => !['completed', 'stopped', 'failed'].includes(j.status));
    if (!active.length) {
      activeJobsContainer.innerHTML = '';
      return;
    }

    let html = `<details class="domain-group" open>
      <summary class="domain-title">
        <span class="domain-name">Active Scans</span>
        <span class="domain-count">${active.length} running</span>
      </summary>
      <div class="session-list">`;

    active.forEach(j => {
      const domain = escapeHtml(j.domain || '…');
      const statusCls = 'badge-' + (j.status === 'running' ? 'running' : 'queued');
      html += `<a class="session-card" href="/run/${encodeURIComponent(j.job_id)}">
        <div class="session-card-main">
          <code class="session-id">${escapeHtml(j.job_id)}</code>
          <span class="badge ${statusCls}">${escapeHtml(STATUS_LABELS[j.status] || j.status)}</span>
          <span class="text-muted" style="font-size:0.85rem">${domain}</span>
        </div>
        <div class="session-card-meta">
          <span class="text-muted">${j.pages_tested} page${j.pages_tested !== 1 ? 's' : ''} tested</span>
          <span class="findings-count ${j.total_findings > 0 ? 'has-findings' : ''}">${j.total_findings} finding${j.total_findings !== 1 ? 's' : ''}</span>
        </div>
      </a>`;
    });

    html += '</div></details>';
    activeJobsContainer.innerHTML = html;
  }

  function loadActiveJobs() {
    fetch('/api/jobs')
      .then(r => r.json())
      .then(data => renderActiveJobs(data.jobs || []))
      .catch(() => {});
  }

  function loadSessions() {
    container.innerHTML = '<div class="spinner" aria-label="Loading sessions"></div>';
    fetch('/api/sessions?limit=200')
      .then(r => {
        if (!r.ok) throw new Error('Server error');
        return r.json();
      })
      .then(data => {
        allSessions = data.sessions || [];
        updateOverview(allSessions);
        applyClientFilters();
      })
      .catch(() => {
        container.innerHTML = `<div class="alert alert-error">
          Failed to load scan sessions.
          <button type="button" id="retry-sessions-btn" class="btn btn-secondary small" style="margin-left:0.5rem">Retry</button>
        </div>`;
        document.getElementById('retry-sessions-btn')?.addEventListener('click', loadSessions);
      });
  }

  loadSessions();
  loadActiveJobs();

  const activeJobsInterval = setInterval(loadActiveJobs, 4000);
  window.addEventListener('pagehide', () => clearInterval(activeJobsInterval));

  let debounce;
  search?.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(applyClientFilters, 180);
  });
  statusFilter?.addEventListener('change', applyClientFilters);
  refreshBtn?.addEventListener('click', () => {
    loadSessions();
    loadActiveJobs();
  });
}());
