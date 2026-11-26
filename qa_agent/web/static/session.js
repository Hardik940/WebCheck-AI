/* WebCheck-AI – Session Detail & Interactive Findings Explorer */
'use strict';

(function () {
  const rows = Array.from(document.querySelectorAll('.finding-row'));
  const searchInput = document.getElementById('finding-search');
  const sevSelect = document.getElementById('filter-severity');
  const verSelect = document.getElementById('filter-verification');
  const catSelect = document.getElementById('filter-category');
  const resetBtn = document.getElementById('reset-finding-filters');
  const toggleAllBtn = document.getElementById('toggle-all-btn');
  const countLabel = document.getElementById('findings-count-label');
  const emptyState = document.getElementById('findings-empty-filter');

  function toggleRow(row, forceState) {
    const detail = row.querySelector('.finding-detail');
    if (!detail) return;
    const expand = forceState !== undefined ? forceState : !row.classList.contains('expanded');
    row.classList.toggle('expanded', expand);
    detail.style.display = expand ? '' : 'none';
  }

  rows.forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('a, button')) return;
      toggleRow(row);
    });
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleRow(row);
      }
    });
  });

  function applyFilters() {
    const query = (searchInput?.value || '').trim().toLowerCase();
    const sev = sevSelect?.value || 'all';
    const ver = verSelect?.value || 'all';
    const cat = catSelect?.value || 'all';

    let visible = 0;
    rows.forEach(row => {
      const matchSev = sev === 'all' || row.dataset.severity === sev;
      const matchVer = ver === 'all' || row.dataset.verification === ver;
      const matchCat = cat === 'all' || row.dataset.category === cat;
      const matchSearch = !query || (row.dataset.search || '').includes(query);

      const show = matchSev && matchVer && matchCat && matchSearch;
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    });

    if (countLabel) {
      countLabel.textContent = `Showing ${visible} of ${rows.length} finding${rows.length !== 1 ? 's' : ''}`;
    }
    if (emptyState) {
      emptyState.style.display = visible === 0 && rows.length > 0 ? '' : 'none';
    }
  }

  searchInput?.addEventListener('input', applyFilters);
  sevSelect?.addEventListener('change', applyFilters);
  verSelect?.addEventListener('change', applyFilters);
  catSelect?.addEventListener('change', applyFilters);

  resetBtn?.addEventListener('click', () => {
    if (searchInput) searchInput.value = '';
    if (sevSelect) sevSelect.value = 'all';
    if (verSelect) verSelect.value = 'all';
    if (catSelect) catSelect.value = 'all';
    applyFilters();
  });

  // Clickable severity bars filter the findings table directly
  document.querySelectorAll('.severity-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!sevSelect) return;
      const targetSev = btn.dataset.severity;
      sevSelect.value = sevSelect.value === targetSev ? 'all' : targetSev;
      applyFilters();
      document.getElementById('findings-tbody')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });

  // Expand / collapse all visible findings
  let allExpanded = false;
  toggleAllBtn?.addEventListener('click', () => {
    allExpanded = !allExpanded;
    rows.forEach(row => {
      if (row.style.display !== 'none') toggleRow(row, allExpanded);
    });
    toggleAllBtn.textContent = allExpanded ? 'Collapse All' : 'Expand All';
  });
}());

// Re-run with same config: pre-fill form on index page
(function () {
  const configEl = document.getElementById('session-config-data');
  const rerunBtn = document.getElementById('rerun-btn');
  if (!configEl || !rerunBtn) return;
  const config = JSON.parse(configEl.textContent);
  rerunBtn.addEventListener('click', e => {
    e.preventDefault();
    if (config.urls && config.urls.length) {
      sessionStorage.setItem('qa_rerun_config', JSON.stringify(config));
      window.location.href = '/';
    }
  });
}());
