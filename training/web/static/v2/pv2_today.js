/* Professional v2 决策台 — 数据填充与图表渲染（仅 textContent，零 XSS 风险） */
(function () {
  const ROOT = location.pathname.startsWith('/training') ? '/training' : '';
  const fmt1 = v => (v === null || v === undefined) ? '-' : (typeof v === 'number' ? v.toFixed(1) : v);

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function fillBullets(id, arr) {
    const el = document.getElementById(id);
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    if (!arr || arr.length === 0) {
      const li = document.createElement('li');
      li.style.color = '#94a3b8';
      li.textContent = '—';
      el.appendChild(li);
      return;
    }
    for (const item of arr) {
      const li = document.createElement('li');
      li.textContent = item;
      el.appendChild(li);
    }
  }

  async function load() {
    let rx = null;
    try {
      const r = await fetch(ROOT + '/api/v2/today');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      rx = await r.json();
    } catch (e) {
      setText('pv2-headline', '加载失败：' + e.message);
      return;
    }
    render(rx);

    fetch(ROOT + '/api/v2/sessions/recent?limit=8').then(r => r.ok ? r.json() : null).then(d => d && renderRecent(d));
    fetch(ROOT + '/api/v2/trends/load?days=90').then(r => r.ok ? r.json() : null).then(d => d && renderPMC(d));
  }

  function render(rx) {
    const conf = rx.confidence || 0;
    setText('pv2-trust-text', `数据可信度 ${(conf * 100).toFixed(0)}/100`);
    const dot = document.getElementById('pv2-trust-dot');
    dot.className = 'pv2-trust-dot ' + (conf >= 0.8 ? '' : (conf >= 0.5 ? 'pv2-trust-dot--medium' : 'pv2-trust-dot--low'));

    const sevs = [
      rx.training && rx.training.load_explained && rx.training.load_explained.severity,
      rx.training && rx.training.polarization_explained && rx.training.polarization_explained.severity,
      rx.rehab && rx.rehab.explained && rx.rehab.explained.severity,
      rx.nutrition && rx.nutrition.explained && rx.nutrition.explained.severity,
    ];
    const card = document.getElementById('pv2-decision');
    const pill = document.getElementById('pv2-risk-pill');
    if (sevs.includes('danger')) {
      card.classList.add('pv2-decision--danger');
      pill.className = 'pv2-pill pv2-pill--danger';
      pill.textContent = 'HIGH RISK';
    } else if (sevs.includes('warn')) {
      card.classList.add('pv2-decision--warn');
      pill.className = 'pv2-pill pv2-pill--warn';
      pill.textContent = 'CAUTION';
    } else {
      pill.textContent = 'GO';
    }
    setText('pv2-headline', rx.verdict || '');
    setText('pv2-summary', (rx.next_actions || []).slice(0, 1).join('') || '');

    const lp = (rx.training && rx.training.load_profile) || {};
    setText('pv2-ctl', fmt1(lp.ctl));
    setText('pv2-atl', fmt1(lp.atl));
    setText('pv2-tsb', fmt1(lp.tsb));
    setText('pv2-acwr', fmt1(lp.acwr_7_28));
    setText('pv2-mono', fmt1(lp.monotony));
    fillBullets('pv2-load-actions', rx.training && rx.training.load_explained && rx.training.load_explained.actions);

    const inj = (rx.rehab && rx.rehab.active_injuries) || [];
    const injBox = document.getElementById('pv2-injuries');
    while (injBox.firstChild) injBox.removeChild(injBox.firstChild);
    if (inj.length === 0) {
      const i = document.createElement('i');
      i.style.color = '#94a3b8';
      i.textContent = '无活跃伤情';
      injBox.appendChild(i);
    } else {
      for (const it of inj) {
        const div = document.createElement('div');
        div.textContent = `${it.site} · ${it.grade} · stage ${it.current_stage} · VAS ${fmt1(it.vas)}`;
        injBox.appendChild(div);
      }
    }
    fillBullets('pv2-rehab-actions', rx.rehab && rx.rehab.explained && rx.rehab.explained.actions);
    fillBullets('pv2-prehab', rx.rehab && rx.rehab.explained && rx.rehab.explained.prehab);

    const eb = (rx.nutrition && rx.nutrition.energy_balance) || {};
    setText('pv2-tdee', fmt1(eb.tdee_kcal));
    setText('pv2-ea', fmt1(eb.ea_kcal_per_kg_ffm));
    const reds = eb.reds_flag || '-';
    const redsBox = document.getElementById('pv2-reds');
    while (redsBox.firstChild) redsBox.removeChild(redsBox.firstChild);
    const span = document.createElement('span');
    span.className = 'pv2-pill ' + (reds === 'red' ? 'pv2-pill--danger' : reds === 'yellow' ? 'pv2-pill--warn' : '');
    span.textContent = String(reds).toUpperCase();
    redsBox.appendChild(span);

    const m = eb.macros_target || {};
    setText('pv2-macros', `CHO ${m.cho_g || '-'}g · PRO ${m.pro_g || '-'}g · FAT ${m.fat_g || '-'}g`);
    fillBullets('pv2-nutri-actions', rx.nutrition && rx.nutrition.explained && rx.nutrition.explained.actions);
    fillBullets('pv2-why', rx.why);

    renderRiskRadar(rx);
  }

  function renderPMC(data) {
    const dom = document.getElementById('pv2-pmc-chart');
    const chart = echarts.init(dom);
    const dates = data.series.map(r => r.date);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['CTL', 'ATL', 'TSB', 'ACWR'], top: 0, textStyle: { color: '#475569' } },
      grid: { left: 50, right: 60, top: 35, bottom: 40 },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 10 } },
      yAxis: [
        { type: 'value', name: 'PMC', splitLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#94a3b8' } },
        { type: 'value', name: 'ACWR', max: 2, splitLine: { show: false }, axisLabel: { color: '#94a3b8' } },
      ],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 6 }],
      series: [
        { name: 'CTL', type: 'line', smooth: true, data: data.series.map(r => r.ctl), itemStyle: { color: '#0f766e' }, areaStyle: { color: 'rgba(15,118,110,.08)' } },
        { name: 'ATL', type: 'line', smooth: true, data: data.series.map(r => r.atl), itemStyle: { color: '#f59e0b' } },
        { name: 'TSB', type: 'line', smooth: true, data: data.series.map(r => r.tsb), itemStyle: { color: '#3b82f6' } },
        { name: 'ACWR', type: 'line', smooth: true, yAxisIndex: 1, data: data.series.map(r => r.acwr), itemStyle: { color: '#dc2626' }, lineStyle: { type: 'dashed' } },
      ],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderRiskRadar(rx) {
    const dom = document.getElementById('pv2-risk-radar');
    const chart = echarts.init(dom);
    const lp = (rx.training && rx.training.load_profile) || {};
    const eb = (rx.nutrition && rx.nutrition.energy_balance) || {};
    const inj = (rx.rehab && rx.rehab.active_injuries) || [];
    const maxVas = Math.max(0, ...inj.map(i => i.vas || 0));
    const acwrRisk = lp.acwr_7_28 ? Math.min(100, Math.abs(lp.acwr_7_28 - 1) * 100) : 0;
    const monoRisk = lp.monotony ? Math.min(100, lp.monotony * 30) : 0;
    const tsbRisk = Math.min(100, Math.max(0, -(lp.tsb || 0) * 2));
    const eaRisk = eb.ea_kcal_per_kg_ffm ? Math.max(0, Math.min(100, (45 - eb.ea_kcal_per_kg_ffm) * 3)) : 0;
    const painRisk = maxVas * 10;
    const conf = (1 - (rx.confidence || 0)) * 100;
    chart.setOption({
      tooltip: {},
      radar: {
        indicator: [
          { name: 'ACWR', max: 100 },
          { name: 'Monotony', max: 100 },
          { name: 'Fatigue', max: 100 },
          { name: 'Energy', max: 100 },
          { name: 'Pain', max: 100 },
          { name: 'Data Gap', max: 100 },
        ],
        axisName: { color: '#475569', fontSize: 11 },
        splitArea: { areaStyle: { color: ['rgba(15,118,110,.02)', 'rgba(15,118,110,.05)'] } },
      },
      series: [{
        type: 'radar',
        data: [{
          value: [acwrRisk, monoRisk, tsbRisk, eaRisk, painRisk, conf],
          name: '风险',
          areaStyle: { color: 'rgba(220,38,38,.18)' },
          lineStyle: { color: '#dc2626' },
        }],
      }],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderRecent(data) {
    const dom = document.getElementById('pv2-recent');
    while (dom.firstChild) dom.removeChild(dom.firstChild);
    if (!data.sessions || data.sessions.length === 0) {
      const i = document.createElement('i');
      i.style.color = '#94a3b8';
      i.textContent = '暂无';
      dom.appendChild(i);
      return;
    }
    const tbl = document.createElement('table');
    tbl.className = 'pv2-table';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    ['日期', '类型', '距离', '时长', 'HR', '配速', 'TSS', ''].forEach(t => {
      const th = document.createElement('th');
      th.textContent = t;
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    tbl.appendChild(thead);
    const tbody = document.createElement('tbody');
    for (const s of data.sessions) {
      const tr = document.createElement('tr');
      const cells = [
        (s.start_time || '').slice(0, 10),
        s.training_type || s.sport || '-',
        ((s.distance_km || 0).toFixed(2)) + ' km',
        Math.round((s.duration_sec || 0) / 60) + ' min',
        s.avg_hr || '-',
        s.avg_pace_sec ? Math.floor(s.avg_pace_sec / 60) + ':' + String(Math.round(s.avg_pace_sec % 60)).padStart(2, '0') : '-',
        (s.hr_tss || 0).toFixed(1),
      ];
      for (const v of cells) {
        const td = document.createElement('td');
        td.textContent = v;
        tr.appendChild(td);
      }
      const tdLink = document.createElement('td');
      const a = document.createElement('a');
      a.href = ROOT + '/v2/sessions/' + s.id;
      a.textContent = '解剖 →';
      tdLink.appendChild(a);
      tr.appendChild(tdLink);
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    dom.appendChild(tbl);
  }

  load();
})();
